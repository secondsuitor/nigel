# drop a database table

def drop_temp_table(table_to_drop):
    import os
    from sqlalchemy import MetaData, Table, create_engine

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL environment variable is not set.')
    engine = create_engine(database_url)
    metadata = MetaData()

    alembic_tmp_post = Table(table_to_drop, metadata, autoload_with=engine)

    alembic_tmp_post.drop(engine)


# flask db heads
# flask db stamp head