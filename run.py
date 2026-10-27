import os
from app import create_app, db

# Create Flask application using the factory pattern
env_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(env_name)

if __name__ == '__main__':
    from database import create_tables, load_ingredients_from_csv
    with app.app_context():
        # Ensure database tables exist and schema is up to date
        create_tables(app)
        # Seed initial ingredients if database is empty
        from app.models.ingredient import Ingredient
        if Ingredient.query.count() == 0:
            load_ingredients_from_csv(app=app)
    
    # Run development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')
    print(f" * Starting IngredientIQ on http://127.0.0.1:{port} (Debug={debug})")
    app.run(host='127.0.0.1', port=port, debug=debug)
