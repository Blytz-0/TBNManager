-- Store per-guild dinosaur master pools
CREATE TABLE guild_dino_pools (
    guild_id BIGINT,
    dinosaur VARCHAR(50),
    PRIMARY KEY (guild_id, dinosaur)
);

-- Store per-server AI restrictions
CREATE TABLE guild_ai_restrictions (
    guild_id BIGINT,
    server_id INT,
    ai_creature VARCHAR(50),
    PRIMARY KEY (guild_id, server_id, ai_creature),
    FOREIGN KEY (server_id) REFERENCES rcon_servers(id) ON DELETE CASCADE
);
