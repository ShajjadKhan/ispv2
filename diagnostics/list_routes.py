import main
for route in main.app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        if 'GET' in route.methods:
            print(f'{route.path:<40} {route.name}')
