-- Store per-server disabled dinosaurs (tracks current state)
CREATE TABLE guild_disabled_dinos (
    guild_id BIGINT,
    server_id INT,
    dinosaur VARCHAR(50),
    PRIMARY KEY (guild_id, server_id, dinosaur),
    FOREIGN KEY (server_id) REFERENCES rcon_servers(id) ON DELETE CASCADE
);
