from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    usuario = db.Column(db.String(50), unique=True, nullable=False, index=True)
    correo = db.Column(db.String(120), unique=True, nullable=False, index=True)
    correo_verificado = db.Column(db.Boolean, default=False, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    acepto_politica = db.Column(db.Boolean, default=False, nullable=False)
    fecha_aceptacion_politica = db.Column(db.DateTime, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_desactivacion = db.Column(db.DateTime, nullable=True)
    codigo_otp = db.Column(db.String(6), nullable=True)
    otp_expiracion = db.Column(db.DateTime, nullable=True)
    otp_email_pendiente = db.Column(db.String(120), nullable=True)
    trxkey_hash = db.Column(db.String(64), nullable=True)
    trxkey_generado_en = db.Column(db.DateTime, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime, nullable=True)
    recovery_codes = db.relationship(
        "RecoveryCode",
        backref="usuario",
        cascade="all, delete-orphan",
        lazy=True,
    )
    actividades = db.relationship(
        "UserActivity",
        backref="usuario",
        cascade="all, delete-orphan",
        lazy=True,
    )
    password_reset_tokens = db.relationship(
        "PasswordResetToken",
        backref="usuario",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def is_active(self):
        return bool(self.activo)


class RecoveryCode(db.Model):
    __tablename__ = "recovery_codes"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id"),
        nullable=False
    )

    codigo_hash = db.Column(db.String(255), nullable=False)

    usado = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    fecha_creacion = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    fecha_uso = db.Column(
        db.DateTime,
        nullable=True
    )


class UserActivity(db.Model):
    __tablename__ = "user_activities"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id"),
        nullable=False,
        index=True,
    )
    accion = db.Column(db.String(80), nullable=False)
    detalle = db.Column(db.String(255), nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id"),
        nullable=False,
        index=True,
    )
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    fecha_expiracion = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_uso = db.Column(db.DateTime, nullable=True)
