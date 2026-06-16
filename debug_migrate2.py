from sqlalchemy import create_engine, inspect, text

engine = create_engine('sqlite:///data/message_gateway.db')

with engine.connect() as conn:
    try:
        result = conn.execute(text("ALTER TABLE channel_configs ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.commit()
        print("created_at added successfully")
    except Exception as e:
        print(f"Error adding created_at: {e}")
    
    try:
        result = conn.execute(text("ALTER TABLE channel_configs ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.commit()
        print("updated_at added successfully")
    except Exception as e:
        print(f"Error adding updated_at: {e}")
    
    try:
        result = conn.execute(text("ALTER TABLE message_records ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.commit()
        print("message_records created_at added successfully")
    except Exception as e:
        print(f"Error adding message_records created_at: {e}")
    
    try:
        result = conn.execute(text("ALTER TABLE message_records ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.commit()
        print("message_records updated_at added successfully")
    except Exception as e:
        print(f"Error adding message_records updated_at: {e}")

inspector = inspect(engine)
print("\nAfter manual ALTER:")
print("channel_configs columns:")
for col in inspector.get_columns('channel_configs'):
    print(f'  {col["name"]}: {col["type"]}')
