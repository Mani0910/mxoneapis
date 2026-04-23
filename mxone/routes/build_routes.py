# routes/build_routes.py

from flask import Blueprint, request
from controllers.build_controller import get_builds_controller, start_download_controller, get_status_controller

build_routes = Blueprint('build_routes', __name__)

build_routes.route('/builds', methods=['GET'])(get_builds_controller)
build_routes.route('/download', methods=['POST'])(lambda: start_download_controller(request))
build_routes.route('/status/<path:ip>', methods=['GET'])(get_status_controller)