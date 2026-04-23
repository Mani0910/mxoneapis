from flask import Flask
from routes.build_routes import build_routes

app = Flask(__name__)
app.register_blueprint(build_routes)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)