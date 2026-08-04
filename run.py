import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", 5000)))
