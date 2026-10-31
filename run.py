import os
from app import create_app, db

# Create Flask application using the factory pattern
env_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(env_name)

# Ensure database tables and schema updates are applied on server startup (both local and Render Gunicorn)
with app.app_context():
    from database import create_tables, load_all_ingredients
    try:
        create_tables(app)
        from app.models.ingredient import Ingredient
        if Ingredient.query.count() < 100:
            load_all_ingredients(app=app)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Startup table verification note: {e}")

if __name__ == '__main__':
    # Run development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')
    print(f" * Starting IngredientIQ on http://127.0.0.1:{port} (Debug={debug})")
    app.run(host='127.0.0.1', port=port, debug=debug)
