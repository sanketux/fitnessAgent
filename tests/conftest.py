import pytest

from fitness_agent import tools
from fitness_agent.db import Database


@pytest.fixture
def db():
    database = Database(":memory:")
    tools.set_database(database)
    yield database
    tools.set_database(None)
    database.close()
