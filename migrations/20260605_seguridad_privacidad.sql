ALTER TABLE usuarios
    ADD COLUMN acepto_politica BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN fecha_aceptacion_politica DATETIME NULL,
    ADD COLUMN activo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN fecha_desactivacion DATETIME NULL;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    token VARCHAR(128) NOT NULL UNIQUE,
    fecha_expiracion DATETIME NOT NULL,
    usado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_creacion DATETIME NOT NULL,
    fecha_uso DATETIME NULL,
    INDEX idx_password_reset_usuario_id (usuario_id),
    INDEX idx_password_reset_token (token),
    CONSTRAINT fk_password_reset_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE CASCADE
);
