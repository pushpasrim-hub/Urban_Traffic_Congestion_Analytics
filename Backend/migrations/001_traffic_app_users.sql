CREATE TABLE IF NOT EXISTS traffic_app_users (
    user_id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    token_version INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_traffic_app_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
