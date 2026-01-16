# ExamSys

ExamSys is an AI-powered online examination system built with Django backend and Firebase Firestore database. It allows administrators to create and manage exams, upload questions, evaluate student answers automatically using AI models, and view detailed analytics. Students can securely take exams, submit answers, and view results.

---

## Features

- Secure Admin and Student login with session management
- Admin Dashboard to upload exam questions (Excel/CSV)
- Dynamic exam code creation and activation/deactivation
- AI-powered automated evaluation of MCQ and descriptive answers
- Persistent admin credential management in Firestore with password reset
- Student exam workflow with exam code and timed sessions
- Real-time analytics and downloadable results for admins
- Responsive UI styled with Tailwind CSS

---

## Technologies Used

- Django (Python) for backend and server-side logic  
- Firebase Firestore as NoSQL cloud database  
- Tailwind CSS for frontend styling  
- Pandas for processing bulk question uploads  
- Python Flask for AI-based answer evaluation microservice  
- JavaScript for interactive UI components

---

## Getting Started

### Prerequisites

- Python 3.8 or higher  
- Firebase account with Firestore enabled  
- Git installed on your system  

### Installation Instructions

1. **Clone the repository**

git clone https://github.com/Bhargav-567/ExamSys.git
cd ExamSys


2. **Create and activate a virtual environment**

python -m venv venv
venv\Scripts\activate


3. **Install dependencies**

pip install -r requirements.txt

- Note: If any error related to setup *wheel* faced, upgrade the python version by running
  ```plaintext

  pip install --upgrade pip setuptools wheel

  python.exe -m pip install --upgrade pip

  ```


4. **Configure Firebase**

- Place your Firebase service account JSON in the project, update your `firebase_config.py` accordingly  
- Ensure Firestore database rules allow read/write as configured for your app

5. **Run the Django server**

python manage.py migrate

python manage.py runserver


6. **Open your browser**

Navigate to http://localhost:8000 to access the system.

---

## Usage

- **Admin:**  
  - Login with admin credentials  
  - Upload exam questions via the dashboard  
  - Create, activate, and deactivate exam codes  
  - Reset admin password securely with register code verification  
  - View analytics and download student results  

- **Student:**  
  - Login with name  
  - Enter exam code to take exams within the allocated time  
  - Submit answers including descriptive questions for AI evaluation  
  - View detailed results with score analytics  

---

## Deployment

- Deploy on any platform supporting Python and Firebase such as Heroku, AWS, Google Cloud, or your own server  
- Use environment variables or secret management for Firebase credentials and Django secret key  
- Use production-grade database rules and HTTPS for secure operation

---

## Contributing

Contributions are welcome! Please fork the repository, make your changes, and create a pull request.

---

## License

This project is licensed under the MIT License.

---

## Contact

For any queries or feature requests, please open an issue or reach out to the maintainer.




