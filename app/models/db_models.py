from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM base class — all mapped models inherit from this."""
    pass
