from .main import app, ctx, require_user, require_write, templates
from .scan_shares import register_scan_routes

register_scan_routes(app, templates, ctx, require_user, require_write)
