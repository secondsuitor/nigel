# drop a database table

def drop_temp_table(table_to_drop):
    from sqlalchemy import MetaData, Table, create_engine

    engine = create_engine('sqlite:///blog.db')  # replace with your database URL
    metadata = MetaData()

    alembic_tmp_post = Table(table_to_drop, metadata, autoload_with=engine)

    alembic_tmp_post.drop(engine)


# flask db heads
# flask db stamp head