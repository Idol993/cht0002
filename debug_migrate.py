from sqlalchemy import create_engine, inspect, text

engine = create_engine('sqlite:///data/message_gateway.db')
inspector = inspect(engine)

print('Tables:', inspector.get_table_names())
print()

print('channel_configs columns:')
for col in inspector.get_columns('channel_configs'):
    print(f'  {col["name"]}: {col["type"]}')
print()

print('message_records columns:')
for col in inspector.get_columns('message_records'):
    print(f'  {col["name"]}: {col["type"]}')

print()
print('Now running migrate_database manually...')

from app.database import migrate_database
migrate_database(engine)

print()
print('After migration:')
print('channel_configs columns:')
for col in inspector.get_columns('channel_configs'):
    print(f'  {col["name"]}: {col["type"]}')
