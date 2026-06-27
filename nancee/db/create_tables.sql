CREATE TABLE user_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    preferred_name TEXT,
    tone TEXT,
    verbosity TEXT,
    preferences_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicle_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    pid TEXT NOT NULL,
    value REAL NOT NULL
);

CREATE TABLE vehicle_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    issue_code TEXT,
    severity TEXT,
    description TEXT,
    recommendation TEXT,
    resolved INTEGER DEFAULT 0
);

-- Indexes
CREATE INDEX idx_vehicle_state_pid ON vehicle_state(pid);
CREATE INDEX idx_vehicle_state_timestamp ON vehicle_state(timestamp);
CREATE INDEX idx_vehicle_state_pid_time ON vehicle_state(pid, timestamp DESC);
