CREATE TABLE IF NOT EXISTS decision_recommendations (
    recommendation_id INT NOT NULL AUTO_INCREMENT,
    segment_id INT NOT NULL,
    priority VARCHAR(20) NOT NULL,
    recommendation_text VARCHAR(500) NOT NULL,
    evidence_summary TEXT NOT NULL,
    problem_type VARCHAR(40) NULL,
    congestion_severity VARCHAR(20) NULL,
    problem_description VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    deduplication_key CHAR(64) NOT NULL,
    PRIMARY KEY (recommendation_id),
    UNIQUE KEY uq_decision_recommendations_deduplication_key (deduplication_key),
    CONSTRAINT fk_decision_recommendations_road_segment
        FOREIGN KEY (segment_id)
        REFERENCES road_segments (segment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
