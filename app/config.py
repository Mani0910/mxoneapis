import os

BUILD_PATH = os.getenv("BUILD_PATH", "/local/home/mxone_admin")
MXONE_REMOTE_DIR = os.getenv("MXONE_REMOTE_DIR", "/local/home/mxone_admin")

# AWS S3
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "AKIA2ZVHHPYE65C47QHJ")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "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")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "mxonebuilds")
AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")
