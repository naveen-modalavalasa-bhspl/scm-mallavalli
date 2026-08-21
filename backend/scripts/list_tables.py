import sys
import os

# Add the backend directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import Base
import app.models  # This should trigger all models to be registered with Base

# Get all tables
tables = Base.metadata.tables.keys()

print("ALL TABLES:")
for t in sorted(tables):
    print(t)
