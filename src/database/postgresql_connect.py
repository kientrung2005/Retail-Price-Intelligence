import psycopg2

class PostgresConnect:
    def __init__(self, host, port, user, password, database="postgres"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

        self.config = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database
        }
        self.connection = None
        self.cursor = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(**self.config)
            self.cursor = self.connection.cursor()
            print(f'--------------Connected to POSTGRES (DB: {self.database})---------------')
            return self.connection, self.cursor
        except psycopg2.Error as e:
            raise Exception(f'------------Fail to connect Postgres: {e}--------------') from e

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection and self.connection.closed == 0:
            self.connection.close()
            print("-----------POSTGRES Close Connection----------")
        self.cursor = None
        self.connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if self.connection:
                self.connection.rollback()
        else:
            if self.connection:
                self.connection.commit()
        self.close()
