"""
Purge expired records from the evidence vault.

Intended to run as a daily cron/job.
"""

from sqlalchemy import create_engine, text

from src.config import settings


def purge_expired() -> int:
    engine = create_engine(settings.postgres_sync_url)
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM evidence_vault WHERE expires_at < NOW()")
        )
        return result.rowcount or 0


if __name__ == "__main__":
    purged = purge_expired()
    print(f"Purged {purged} expired evidence_vault records.")
