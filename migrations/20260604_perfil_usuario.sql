ALTER TABLE usuarios
    ADD COLUMN correo_verificado TINYINT(1) NOT NULL DEFAULT 0 AFTER correo,
    ADD COLUMN otp_email_pendiente VARCHAR(120) NULL AFTER otp_expiracion,
    ADD COLUMN trxkey_hash VARCHAR(64) NULL AFTER otp_email_pendiente,
    ADD COLUMN trxkey_generado_en DATETIME NULL AFTER trxkey_hash;

CREATE TABLE IF NOT EXISTS user_activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    accion VARCHAR(80) NOT NULL,
    detalle VARCHAR(255) NULL,
    ip VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_user_activities_usuario_id (usuario_id),
    INDEX ix_user_activities_fecha (fecha),
    CONSTRAINT fk_user_activities_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE CASCADE
);
