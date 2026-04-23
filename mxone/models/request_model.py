# models/request_model.py

def validate_request(data):
    required_fields = ["build_name", "ip", "username", "password"]

    for field in required_fields:
        if field not in data:
            return False, f"{field} is missing"

    return True, None