-- Migration 051: Add ON DELETE CASCADE to community tables and notifications
-- Required for GDPR Article 17 compliance: user deletion must cascade to all
-- user-owned data. Also adds FK to notifications table (was missing).

-- community_posts: drop plain FK, re-add with CASCADE
ALTER TABLE community_posts
    DROP CONSTRAINT IF EXISTS community_posts_user_id_fkey;
ALTER TABLE community_posts
    ADD CONSTRAINT community_posts_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- community_votes: drop plain FK, re-add with CASCADE
ALTER TABLE community_votes
    DROP CONSTRAINT IF EXISTS community_votes_user_id_fkey;
ALTER TABLE community_votes
    ADD CONSTRAINT community_votes_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- community_reports: drop plain FK, re-add with CASCADE
ALTER TABLE community_reports
    DROP CONSTRAINT IF EXISTS community_reports_user_id_fkey;
ALTER TABLE community_reports
    ADD CONSTRAINT community_reports_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- notifications: add FK with CASCADE (was missing entirely)
ALTER TABLE notifications
    ADD CONSTRAINT notifications_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Grants
GRANT ALL ON community_posts TO neondb_owner;
GRANT ALL ON community_votes TO neondb_owner;
GRANT ALL ON community_reports TO neondb_owner;
GRANT ALL ON notifications TO neondb_owner;
