from flask import Flask, request, jsonify
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://RamaReddi:@localhost/worki'
app.config['JWT_SECRET_KEY'] = 'your_secret_key_here'  # Replace with a secure secret key
db = SQLAlchemy(app)
jwt = JWTManager(app)

# Define the User model with an 'role' column
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'

# Define the Book model (assuming you have a Book model)
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    isbn = db.Column(db.String(13), unique=True, nullable=False)

# Define the Booking model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    issue_time = db.Column(db.DateTime, nullable=False)
    return_time = db.Column(db.DateTime, nullable=False)

    # Define a constructor to create a new booking
    def __init__(self, book_id, user_id, issue_time, return_time):
        self.book_id = book_id
        self.user_id = user_id
        self.issue_time = issue_time
        self.return_time = return_time


# Your admin API key (replace with your actual admin API key)
ADMIN_API_KEY = 'your_admin_api_key'

# Define an endpoint for user registration
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    role = data.get('role', 'user')  # Default role is 'user' if not provided

    existing_user = User.query.filter_by(username=username).first()
    existing_email = User.query.filter_by(email=email).first()

    if existing_user or existing_email:
        return jsonify({"status": "Username or email already exists", "status_code": 400}), 400

    new_user = User(username=username, password=password, email=email, role=role)

    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"status": "Account successfully created", "status_code": 200, "user_id": new_user.id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "Error creating account", "status_code": 500}), 500

# Define an endpoint for user login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and user.password == password:
        access_token = create_access_token(identity=user.id)
        return jsonify({"status": "Login successful", "status_code": 200, "user_id": user.id, "access_token": access_token}), 200
    else:
        return jsonify({"status": "Incorrect username/password provided. Please retry", "status_code": 401}), 401

# Protect an admin endpoint using API key (Add a New Book)
@app.route('/api/books/create', methods=['POST'])
def create_book():
    api_key = request.headers.get('API-Key')

    # Check if the API key is valid for admin access
    if api_key != ADMIN_API_KEY:
        return jsonify({"status": "Unauthorized access", "status_code": 401}), 401

    data = request.get_json()
    title = data.get('title')
    author = data.get('author')
    isbn = data.get('isbn')

    # Create a new book record in the database
    new_book = Book(title=title, author=author, isbn=isbn)

    try:
        db.session.add(new_book)
        db.session.commit()
        return jsonify({"message": "Book added successfully", "book_id": new_book.id}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({"status": "Book with the same ISBN already exists", "status_code": 400}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "Error adding book", "status_code": 500}), 500

# Define an endpoint to search books by title
@app.route('/api/books', methods=['GET'])
def search_books_by_title():
    search_query = request.args.get('title')

    if not search_query:
        return jsonify({"status": "Missing search_query parameter", "status_code": 400}), 400

    # Query the database to find books whose titles contain the search keywords
    books = Book.query.filter(Book.title.ilike(f"%{search_query}%")).all()

    if not books:
        return jsonify({"status": "No books found matching the search query", "status_code": 404}), 404

    # Create a list of book data to include in the response
    results = []
    for book in books:
        results.append({
            "book_id": book.id,
            "title": book.title,
            "author": book.author,
            "isbn": book.isbn
        })

    return jsonify({"results": results}), 200

# Define an endpoint to allow users to borrow a book
@app.route('/api/books/borrow', methods=['POST'])
@jwt_required()
def borrow_book():
    current_user_id = get_jwt_identity()
    data = request.get_json()

    book_id = data.get('book_id')
    user_id = data.get('user_id')
    issue_time = data.get('issue_time')
    return_time = data.get('return_time')

    # Check if the book is available
    book = Book.query.filter_by(id=book_id).first()
    if not book:
        return jsonify({"status": "Book not found", "status_code": 404}), 404

    # Check if the book is already booked during the specified period
    existing_booking = Booking.query.filter(
        Booking.book_id == book_id,
        (Booking.issue_time <= return_time) & (Booking.return_time >= issue_time)
    ).first()

    if existing_booking:
        return jsonify({"status": "Book is not available at this moment", "status_code": 400}), 400

    # Book the book
    new_booking = Booking(book_id=book_id, user_id=current_user_id, issue_time=issue_time, return_time=return_time)

    try:
        db.session.add(new_booking)
        db.session.commit()
        return jsonify({"status": "Book booked successfully", "status_code": 200, "booking_id": new_booking.id}), 200
    except Exception as e:
        db.session.rollback()
        return str(e)

@app.route('/api/books/<int:book_id>/availability', methods=['GET'])
def get_book_availability(book_id):
    # Find the book by its ID
    book = Book.query.filter_by(id=book_id).first()

    if not book:
        return jsonify({"status": "Book not found", "status_code": 404}), 404

    # Check if the book is available
    current_time = datetime.utcnow()
    is_available = not Booking.query.filter(
        Booking.book_id == book_id,
        (Booking.issue_time <= current_time) & (Booking.return_time >= current_time)
    ).first()

    response_data = {
        "book_id": str(book.id),
        "title": book.title,
        "author": book.author,
        "available": is_available
    }

    if not is_available:
        next_available_booking = Booking.query.filter(
            Booking.book_id == book_id,
            Booking.issue_time > current_time
        ).order_by(Booking.issue_time).first()

        if next_available_booking:
            response_data["next_available_at"] = next_available_booking.issue_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    return jsonify(response_data), 200



if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
