import base64
from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import json
import os
import random
import secrets
import string

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_mail import Mail, Message
from google import genai
from google.genai import types
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

from models import PasswordResetToken, RecoveryCode, UserActivity, Usuario, db


app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def load_local_env():
    env_path = os.path.join(app.root_path, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
    "MAIL_DEFAULT_SENDER",
    app.config["MAIL_USERNAME"],
)
app.config["MAIL_SUPPRESS_SEND"] = os.getenv("MAIL_SUPPRESS_SEND", "false").lower() == "true"

db.init_app(app)
with app.app_context():
    result = db.session.execute(text("SELECT DATABASE()"))
    print("triax:", result.scalar())
mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesion para acceder al sistema."
login_manager.login_message_category = "warning"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


def generar_codigo_otp():
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def get_fernet():
    configured_key = os.getenv("TRXKEY_FERNET_KEY")
    if configured_key:
        return Fernet(configured_key.encode())

    digest = hashlib.sha256(app.config["SECRET_KEY"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def hash_bytes(contenido):
    return hashlib.sha256(contenido).hexdigest()


def registrar_actividad(usuario_id, accion, detalle=None):
    db.session.add(
        UserActivity(
            usuario_id=usuario_id,
            accion=accion,
            detalle=detalle,
            ip=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=(request.user_agent.string or "")[:255],
        )
    )


def generar_trxkey(usuario):
    payload = {
        "id_usuario": usuario.id,
        "usuario": usuario.usuario,
        "correo": usuario.correo,
        "fecha_generacion": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    contenido = get_fernet().encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    usuario.trxkey_hash = hash_bytes(contenido)
    usuario.trxkey_generado_en = datetime.utcnow()
    return contenido


def validar_trxkey(usuario, archivo):
    if not usuario.trxkey_hash:
        return False

    contenido = archivo.read()
    if not contenido or hash_bytes(contenido) != usuario.trxkey_hash:
        return False

    try:
        payload = json.loads(get_fernet().decrypt(contenido).decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
        return False

    return (
        payload.get("id_usuario") == usuario.id
        and payload.get("usuario") == usuario.usuario
        and payload.get("correo") == usuario.correo
    )


def generar_codigo_recuperacion():
    alfabeto = string.ascii_uppercase + string.digits
    bloques = []
    for _ in range(3):
        bloques.append("".join(secrets.choice(alfabeto) for _ in range(4)))
    return "-".join(bloques)


def normalizar_codigo_recuperacion(codigo):
    return codigo.strip().upper()


def crear_recovery_codes(usuario_id, cantidad=10):
    RecoveryCode.query.filter_by(usuario_id=usuario_id).delete()
    codigos_visibles = [generar_codigo_recuperacion() for _ in range(cantidad)]

    for codigo in codigos_visibles:
        db.session.add(
            RecoveryCode(
                usuario_id=usuario_id,
                codigo_hash=generate_password_hash(normalizar_codigo_recuperacion(codigo)),
            )
        )

    db.session.commit()
    return codigos_visibles


def descargar_texto(nombre_archivo, contenido):
    archivo = BytesIO(contenido.encode("utf-8"))
    archivo.seek(0)
    return send_file(
        archivo,
        mimetype="text/plain; charset=utf-8",
        as_attachment=True,
        download_name=nombre_archivo,
    )


def buscar_recovery_code_valido(usuario_id, codigo):
    codigo_normalizado = normalizar_codigo_recuperacion(codigo)
    codigos_no_usados = RecoveryCode.query.filter_by(
        usuario_id=usuario_id,
        usado=False,
    ).all()

    for recovery_code in codigos_no_usados:
        if check_password_hash(recovery_code.codigo_hash, codigo_normalizado):
            return recovery_code

    return None


def enviar_codigo_otp(usuario):
    mensaje = Message(
        subject="Código de acceso TRIAX IA",
        recipients=[usuario.correo],
    )
    mensaje.body = f"""Hola {usuario.nombre}.

Su código de verificación es:

{usuario.codigo_otp}

Este código expirará en 5 minutos.
"""
    mail.send(mensaje)


def enviar_codigo_verificacion_correo(usuario, destino=None):
    destinatario = destino or usuario.correo
    mensaje = Message(
        subject="Verificacion de correo TRIAX IA",
        recipients=[destinatario],
    )
    mensaje.body = f"""Hola {usuario.nombre}.

Tu codigo de verificacion de correo es:

{usuario.codigo_otp}

Este codigo expirara en 5 minutos.
"""
    mail.send(mensaje)


def limpiar_otp(usuario):
    usuario.codigo_otp = None
    usuario.otp_expiracion = None


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generar_token_restablecimiento(usuario):
    token = secrets.token_urlsafe(48)
    db.session.add(
        PasswordResetToken(
            usuario_id=usuario.id,
            token=token_hash(token),
            fecha_expiracion=datetime.utcnow() + timedelta(minutes=30),
        )
    )
    return token


def enviar_enlace_restablecimiento(usuario, token):
    enlace = url_for("restablecer_password", token=token, _external=True)
    mensaje = Message(
        subject="Restablecer contrasena TRIAX IA",
        recipients=[usuario.correo],
    )
    mensaje.body = f"""Hola {usuario.nombre}.

Recibimos una solicitud para restablecer tu contrasena en TRIAX IA.

Usa este enlace durante los proximos 30 minutos:
{enlace}

Si no solicitaste este cambio, puedes ignorar este mensaje.
"""
    mail.send(mensaje)


def password_valida(password, confirmar_password):
    if len(password) < 8:
        return "La contrasena debe tener minimo 8 caracteres."
    if password != confirmar_password:
        return "La confirmacion de contrasena no coincide."
    return None


def asegurar_esquema_seguridad():
    inspector = inspect(db.engine)
    if not inspector.has_table("usuarios"):
        return

    columnas = {columna["name"] for columna in inspector.get_columns("usuarios")}
    dialecto = db.engine.dialect.name
    definiciones = {
        "acepto_politica": "BOOLEAN NOT NULL DEFAULT FALSE",
        "fecha_aceptacion_politica": "DATETIME NULL",
        "activo": "BOOLEAN NOT NULL DEFAULT TRUE",
        "fecha_desactivacion": "DATETIME NULL",
    }

    if dialecto == "sqlite":
        definiciones["acepto_politica"] = "BOOLEAN NOT NULL DEFAULT 0"
        definiciones["activo"] = "BOOLEAN NOT NULL DEFAULT 1"

    for columna, definicion in definiciones.items():
        if columna not in columnas:
            db.session.execute(text(f"ALTER TABLE usuarios ADD COLUMN {columna} {definicion}"))

    db.session.commit()


@app.before_request
def crear_tablas():
    pass

    if current_user.is_authenticated and not current_user.activo:
        session.clear()
        logout_user()
        flash("Tu cuenta esta desactivada. Contacta al administrador si necesitas soporte.", "warning")
        return redirect(url_for("login"))


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/politica-datos")
def politica_datos():
    return render_template("politica_datos.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("mostrar_modelo"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        usuario = request.form.get("usuario", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        confirmar_password = request.form.get("confirmar_password", "")
        acepto_politica = request.form.get("acepto_politica") == "on"

        if not nombre or not usuario or not correo or not password or not confirmar_password:
            flash("Todos los campos son obligatorios.", "error")
        elif not acepto_politica:
            flash("Debes aceptar la Politica de Tratamiento de Datos para registrarte.", "error")
        else:
            error_password = password_valida(password, confirmar_password)
            if error_password:
                flash(error_password, "error")
            elif Usuario.query.filter_by(usuario=usuario).first():
                flash("El usuario ya esta registrado.", "error")
            elif Usuario.query.filter_by(correo=correo).first():
                flash("El correo electronico ya esta registrado.", "error")
            else:
                nuevo_usuario = Usuario(
                    nombre=nombre,
                    usuario=usuario,
                    correo=correo,
                    password_hash=generate_password_hash(password),
                    acepto_politica=True,
                    fecha_aceptacion_politica=datetime.utcnow(),
                )
                db.session.add(nuevo_usuario)
                db.session.commit()
                codigos_recuperacion = crear_recovery_codes(nuevo_usuario.id)
                return render_template(
                    "recovery_codes.html",
                    codigos=codigos_recuperacion,
                    es_regeneracion=False,
                )

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("mostrar_modelo"))

    if request.method == "POST":
        usuario_form = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        metodo = request.form.get("metodo", "otp")
        usuario = Usuario.query.filter_by(usuario=usuario_form).first()

        if not usuario or not check_password_hash(usuario.password_hash, password):
            flash("Usuario o contrasena incorrectos.", "error")
            return render_template("login.html")

        if not usuario.activo:
            flash("Esta cuenta esta desactivada y no puede iniciar sesion.", "error")
            return render_template("login.html")

        if metodo == "recovery":
            codigo = request.form.get("codigo_recuperacion", "")
            recovery_code = buscar_recovery_code_valido(usuario.id, codigo)
            if not recovery_code:
                flash("El codigo de recuperacion no existe, ya fue usado o no coincide.", "error")
                return render_template("login.html")

            recovery_code.usado = True
            recovery_code.fecha_uso = datetime.utcnow()
            limpiar_otp(usuario)
            usuario.ultimo_acceso = datetime.utcnow()
            registrar_actividad(usuario.id, "login_recovery", "Acceso con codigo de recuperacion")
            db.session.commit()
            session.pop("otp_user_id", None)
            login_user(usuario)
            flash("Acceso recuperado correctamente. Regenera tus codigos si te quedan pocos.", "success")
            return redirect(url_for("mostrar_modelo"))

        if metodo == "trxkey":
            archivo = request.files.get("trxkey")
            if not archivo or not validar_trxkey(usuario, archivo):
                registrar_actividad(usuario.id, "login_trxkey_fallido", "Archivo .trxkey invalido")
                db.session.commit()
                flash("El archivo .trxkey no coincide o fue reemplazado.", "error")
                return render_template("login.html")

            limpiar_otp(usuario)
            usuario.ultimo_acceso = datetime.utcnow()
            registrar_actividad(usuario.id, "login_trxkey", "Acceso con archivo de identidad TRIAX")
            db.session.commit()
            session.pop("otp_user_id", None)
            login_user(usuario)
            flash("Acceso verificado con archivo TRIAX.", "success")
            return redirect(url_for("mostrar_modelo"))

        usuario.codigo_otp = generar_codigo_otp()
        usuario.otp_expiracion = datetime.utcnow() + timedelta(minutes=5)
        db.session.commit()

        try:
            enviar_codigo_otp(usuario)
        except Exception as exc:
            limpiar_otp(usuario)
            db.session.commit()
            flash(f"No se pudo enviar el codigo OTP: {exc}", "error")
            return render_template("login.html")

        session["otp_user_id"] = usuario.id
        flash("Enviamos un codigo de verificacion a tu correo.", "success")
        return redirect(url_for("verificar_otp"))

    return render_template("login.html")


@app.route("/verificar-otp", methods=["GET", "POST"])
def verificar_otp():
    if current_user.is_authenticated:
        return redirect(url_for("mostrar_modelo"))

    usuario_id = session.get("otp_user_id")
    if not usuario_id:
        flash("Primero inicia sesion para recibir el codigo OTP.", "warning")
        return redirect(url_for("login"))

    usuario = db.session.get(Usuario, usuario_id)
    if not usuario:
        session.pop("otp_user_id", None)
        flash("No se encontro el usuario asociado al codigo.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        codigo = request.form.get("codigo_otp", "").strip()

        if not usuario.codigo_otp or not usuario.otp_expiracion:
            flash("No hay un codigo activo. Inicia sesion nuevamente.", "error")
            return redirect(url_for("login"))

        if datetime.utcnow() > usuario.otp_expiracion:
            limpiar_otp(usuario)
            db.session.commit()
            session.pop("otp_user_id", None)
            flash("El codigo OTP expiro. Inicia sesion nuevamente.", "error")
            return redirect(url_for("login"))

        if codigo != usuario.codigo_otp:
            flash("El codigo OTP es incorrecto.", "error")
            return render_template("verificar_otp.html")

        limpiar_otp(usuario)
        usuario.ultimo_acceso = datetime.utcnow()
        usuario.correo_verificado = True
        registrar_actividad(usuario.id, "login_otp", "Acceso con OTP por correo")
        db.session.commit()
        session.pop("otp_user_id", None)
        login_user(usuario)
        flash("Acceso verificado correctamente.", "success")
        return redirect(url_for("mostrar_modelo"))

    return render_template("verificar_otp.html")


@app.route("/recovery-login", methods=["GET", "POST"])
def recovery_login():
    if current_user.is_authenticated:
        return redirect(url_for("mostrar_modelo"))

    if request.method == "POST":
        usuario_form = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        codigo = request.form.get("codigo_recuperacion", "")
        usuario = Usuario.query.filter_by(usuario=usuario_form).first()

        if not usuario or not check_password_hash(usuario.password_hash, password):
            flash("Usuario o contrasena incorrectos.", "error")
            return render_template("recovery_login.html")

        if not usuario.activo:
            flash("Esta cuenta esta desactivada y no puede iniciar sesion.", "error")
            return render_template("recovery_login.html")

        recovery_code = buscar_recovery_code_valido(usuario.id, codigo)
        if not recovery_code:
            flash("El codigo de recuperacion no existe, ya fue usado o no coincide.", "error")
            return render_template("recovery_login.html")

        recovery_code.usado = True
        recovery_code.fecha_uso = datetime.utcnow()
        limpiar_otp(usuario)
        usuario.ultimo_acceso = datetime.utcnow()
        registrar_actividad(usuario.id, "login_recovery", "Acceso con codigo de recuperacion")
        db.session.commit()

        session.pop("otp_user_id", None)
        login_user(usuario)
        flash("Acceso recuperado correctamente. Regenera tus codigos si te quedan pocos.", "success")
        return redirect(url_for("mostrar_modelo"))

    return render_template("recovery_login.html")


@app.route("/olvide-password", methods=["GET", "POST"])
def olvide_password():
    if current_user.is_authenticated:
        return redirect(url_for("mostrar_modelo"))

    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        usuario = Usuario.query.filter_by(correo=correo).first()

        if usuario and usuario.activo:
            token = generar_token_restablecimiento(usuario)
            registrar_actividad(usuario.id, "password_reset_solicitado", "Enlace de restablecimiento generado")
            try:
                enviar_enlace_restablecimiento(usuario, token)
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                flash(f"No se pudo enviar el correo de recuperacion: {exc}", "error")
                return render_template("olvide_password.html")

        flash("Si el correo esta registrado, enviaremos un enlace para restablecer la contrasena.", "success")
        return redirect(url_for("login"))

    return render_template("olvide_password.html")


@app.route("/reactivar-cuenta", methods=["GET", "POST"])
def reactivar_cuenta():
    if current_user.is_authenticated:
        return redirect(url_for("mostrar_modelo"))

    paso = request.args.get("paso", "credenciales")

    if request.method == "POST" and paso == "otp":
        usuario_id = session.get("reactivate_user_id")
        usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
        codigo = request.form.get("codigo_otp", "").strip()

        if not usuario:
            session.pop("reactivate_user_id", None)
            flash("Inicia nuevamente el proceso de reactivacion.", "error")
            return redirect(url_for("reactivar_cuenta"))
        if not usuario.codigo_otp or not usuario.otp_expiracion:
            flash("No hay un codigo OTP activo.", "error")
            return redirect(url_for("reactivar_cuenta"))
        if datetime.utcnow() > usuario.otp_expiracion:
            limpiar_otp(usuario)
            db.session.commit()
            session.pop("reactivate_user_id", None)
            flash("El codigo OTP expiro. Inicia nuevamente el proceso.", "error")
            return redirect(url_for("reactivar_cuenta"))
        if codigo != usuario.codigo_otp:
            flash("El codigo OTP es incorrecto.", "error")
            return render_template("reactivar_cuenta.html", paso="otp")

        usuario.activo = True
        usuario.fecha_desactivacion = None
        usuario.ultimo_acceso = datetime.utcnow()
        limpiar_otp(usuario)
        registrar_actividad(usuario.id, "cuenta_reactivada", "Cuenta reactivada con OTP")
        db.session.commit()
        session.pop("reactivate_user_id", None)
        login_user(usuario)
        flash("Tu cuenta fue reactivada correctamente.", "success")
        return redirect(url_for("mostrar_modelo"))

    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip().lower()
        password = request.form.get("password", "")
        usuario = Usuario.query.filter(
            (Usuario.usuario == identificador) | (Usuario.correo == identificador)
        ).first()

        if not usuario or not check_password_hash(usuario.password_hash, password):
            flash("Usuario, correo o contrasena incorrectos.", "error")
            return render_template("reactivar_cuenta.html", paso="credenciales")
        if usuario.activo:
            flash("Esta cuenta ya esta activa. Puedes iniciar sesion normalmente.", "success")
            return redirect(url_for("login"))

        usuario.codigo_otp = generar_codigo_otp()
        usuario.otp_expiracion = datetime.utcnow() + timedelta(minutes=5)
        try:
            enviar_codigo_otp(usuario)
        except Exception as exc:
            limpiar_otp(usuario)
            db.session.commit()
            flash(f"No se pudo enviar el codigo OTP: {exc}", "error")
            return render_template("reactivar_cuenta.html", paso="credenciales")

        session["reactivate_user_id"] = usuario.id
        registrar_actividad(usuario.id, "reactivacion_otp_enviado", "OTP enviado para reactivar cuenta")
        db.session.commit()
        flash("Enviamos un codigo OTP a tu correo para reactivar la cuenta.", "success")
        return redirect(url_for("reactivar_cuenta", paso="otp"))

    return render_template("reactivar_cuenta.html", paso=paso)


@app.route("/restablecer-password/<token>", methods=["GET", "POST"])
def restablecer_password(token):
    token_bd = PasswordResetToken.query.filter_by(token=token_hash(token)).first()

    if not token_bd or token_bd.usado or datetime.utcnow() > token_bd.fecha_expiracion:
        flash("El enlace de restablecimiento no existe o ya expiro.", "error")
        return redirect(url_for("olvide_password"))

    usuario = token_bd.usuario
    if not usuario or not usuario.activo:
        flash("No es posible restablecer la contrasena de esta cuenta.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirmar_password = request.form.get("confirmar_password", "")
        error_password = password_valida(password, confirmar_password)

        if error_password:
            flash(error_password, "error")
            return render_template("restablecer_password.html")

        usuario.password_hash = generate_password_hash(password)
        token_bd.usado = True
        token_bd.fecha_uso = datetime.utcnow()
        limpiar_otp(usuario)
        registrar_actividad(usuario.id, "password_restablecido", "Contrasena actualizada con token")
        db.session.commit()
        flash("Tu contrasena fue restablecida correctamente. Ya puedes iniciar sesion.", "success")
        return redirect(url_for("login"))

    return render_template("restablecer_password.html")


@app.route("/logout")
@login_required
def logout():
    registrar_actividad(current_user.id, "logout", "Sesion cerrada")
    db.session.commit()
    logout_user()
    flash("Sesion cerrada correctamente.", "success")
    return redirect(url_for("login"))


@app.route("/modelo")
@login_required
def mostrar_modelo():
    return render_template("modelo.html")


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    if request.method == "POST":
        accion = request.form.get("accion")

        if accion == "actualizar_personal":
            nombre = request.form.get("nombre", "").strip()
            if not nombre:
                flash("El nombre no puede estar vacio.", "error")
            else:
                current_user.nombre = nombre
                registrar_actividad(current_user.id, "perfil_actualizado", "Informacion personal actualizada")
                db.session.commit()
                flash("Informacion personal actualizada.", "success")
            return redirect(url_for("perfil", tab="personal"))

        if accion == "actualizar_correo":
            nuevo_correo = request.form.get("correo", "").strip().lower()
            if not nuevo_correo:
                flash("El correo no puede estar vacio.", "error")
            elif Usuario.query.filter(Usuario.correo == nuevo_correo, Usuario.id != current_user.id).first():
                flash("Ese correo ya esta registrado.", "error")
            else:
                current_user.codigo_otp = generar_codigo_otp()
                current_user.otp_expiracion = datetime.utcnow() + timedelta(minutes=5)
                current_user.otp_email_pendiente = nuevo_correo
                try:
                    enviar_codigo_verificacion_correo(current_user, nuevo_correo)
                except Exception as exc:
                    limpiar_otp(current_user)
                    current_user.otp_email_pendiente = None
                    db.session.commit()
                    flash(f"No se pudo enviar el codigo de verificacion: {exc}", "error")
                    return redirect(url_for("perfil", tab="seguridad"))

                registrar_actividad(current_user.id, "correo_pendiente", f"Verificacion enviada a {nuevo_correo}")
                db.session.commit()
                flash("Enviamos un codigo al nuevo correo. Verificalo para activar el cambio.", "success")
            return redirect(url_for("perfil", tab="seguridad"))

        if accion == "verificar_correo":
            codigo = request.form.get("codigo_otp", "").strip()
            if not current_user.codigo_otp or not current_user.otp_expiracion:
                flash("No hay un codigo de verificacion activo.", "error")
            elif datetime.utcnow() > current_user.otp_expiracion:
                limpiar_otp(current_user)
                current_user.otp_email_pendiente = None
                db.session.commit()
                flash("El codigo expiro. Solicita uno nuevo.", "error")
            elif codigo != current_user.codigo_otp:
                flash("El codigo de verificacion es incorrecto.", "error")
            else:
                if current_user.otp_email_pendiente:
                    current_user.correo = current_user.otp_email_pendiente
                    current_user.otp_email_pendiente = None
                current_user.correo_verificado = True
                limpiar_otp(current_user)
                registrar_actividad(current_user.id, "correo_verificado", "Correo activado")
                db.session.commit()
                flash("Correo verificado correctamente.", "success")
            return redirect(url_for("perfil", tab="seguridad"))

    codigos_disponibles = RecoveryCode.query.filter_by(
        usuario_id=current_user.id,
        usado=False,
    ).count()
    codigos_usados = RecoveryCode.query.filter_by(
        usuario_id=current_user.id,
        usado=True,
    ).count()
    actividades = (
        UserActivity.query.filter_by(usuario_id=current_user.id)
        .order_by(UserActivity.fecha.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "perfil.html",
        tab_activa=request.args.get("tab", "personal"),
        codigos_disponibles=codigos_disponibles,
        codigos_usados=codigos_usados,
        actividades=actividades,
    )


@app.route("/seguridad")
@login_required
def seguridad():
    codigos_disponibles = RecoveryCode.query.filter_by(
        usuario_id=current_user.id,
        usado=False,
    ).count()
    codigos_usados = RecoveryCode.query.filter_by(
        usuario_id=current_user.id,
        usado=True,
    ).count()
    return render_template(
        "seguridad.html",
        codigos_disponibles=codigos_disponibles,
        codigos_usados=codigos_usados,
        flujo_eliminacion=request.args.get("eliminar"),
    )


@app.route("/seguridad/desactivar", methods=["POST"])
@login_required
def desactivar_cuenta():
    password = request.form.get("password", "")

    if not check_password_hash(current_user.password_hash, password):
        flash("La contrasena actual no es correcta.", "error")
        return redirect(url_for("seguridad"))

    current_user.activo = False
    current_user.fecha_desactivacion = datetime.utcnow()
    registrar_actividad(current_user.id, "cuenta_desactivada", "Cuenta desactivada por el usuario")
    db.session.commit()
    session.clear()
    logout_user()
    flash("Tu cuenta ha sido desactivada correctamente", "success")
    return redirect(url_for("login"))


@app.route("/seguridad/eliminar/iniciar", methods=["POST"])
@login_required
def eliminar_cuenta_iniciar():
    password = request.form.get("password", "")

    if not check_password_hash(current_user.password_hash, password):
        flash("La contrasena actual no es correcta.", "error")
        return redirect(url_for("seguridad", eliminar="password"))

    current_user.codigo_otp = generar_codigo_otp()
    current_user.otp_expiracion = datetime.utcnow() + timedelta(minutes=5)
    session["delete_account_password_ok"] = True

    try:
        enviar_codigo_otp(current_user)
    except Exception as exc:
        limpiar_otp(current_user)
        session.pop("delete_account_password_ok", None)
        db.session.commit()
        flash(f"No se pudo enviar el codigo OTP: {exc}", "error")
        return redirect(url_for("seguridad"))

    registrar_actividad(current_user.id, "eliminacion_otp_enviado", "OTP enviado para eliminar cuenta")
    db.session.commit()
    flash("Enviamos un codigo OTP a tu correo para continuar.", "success")
    return redirect(url_for("seguridad", eliminar="otp"))


@app.route("/seguridad/eliminar/verificar", methods=["POST"])
@login_required
def eliminar_cuenta_verificar():
    if not session.get("delete_account_password_ok"):
        flash("Primero valida tu contrasena para iniciar la eliminacion.", "warning")
        return redirect(url_for("seguridad", eliminar="password"))

    codigo = request.form.get("codigo_otp", "").strip()
    if not current_user.codigo_otp or not current_user.otp_expiracion:
        flash("No hay un codigo OTP activo.", "error")
        return redirect(url_for("seguridad", eliminar="password"))
    if datetime.utcnow() > current_user.otp_expiracion:
        limpiar_otp(current_user)
        session.pop("delete_account_password_ok", None)
        db.session.commit()
        flash("El codigo OTP expiro. Inicia el proceso nuevamente.", "error")
        return redirect(url_for("seguridad", eliminar="password"))
    if codigo != current_user.codigo_otp:
        flash("El codigo OTP es incorrecto.", "error")
        return redirect(url_for("seguridad", eliminar="otp"))

    limpiar_otp(current_user)
    session["delete_account_otp_ok"] = True
    db.session.commit()
    flash("OTP verificado. Confirma la eliminacion definitiva.", "success")
    return redirect(url_for("seguridad", eliminar="confirmar"))


@app.route("/seguridad/eliminar/confirmar", methods=["POST"])
@login_required
def eliminar_cuenta_confirmar():
    if not session.get("delete_account_password_ok") or not session.get("delete_account_otp_ok"):
        flash("Debes completar la validacion de contrasena y OTP.", "warning")
        return redirect(url_for("seguridad", eliminar="password"))

    confirmacion = request.form.get("confirmacion", "").strip().upper()
    if confirmacion != "ELIMINAR":
        flash("Escribe ELIMINAR para confirmar esta accion irreversible.", "error")
        return redirect(url_for("seguridad", eliminar="confirmar"))

    usuario_id = current_user.id
    usuario = db.session.get(Usuario, usuario_id)
    RecoveryCode.query.filter_by(usuario_id=usuario_id).delete()
    PasswordResetToken.query.filter_by(usuario_id=usuario_id).delete()
    UserActivity.query.filter_by(usuario_id=usuario_id).delete()
    if usuario:
        usuario.trxkey_hash = None
        usuario.trxkey_generado_en = None
        db.session.delete(usuario)
    db.session.commit()
    session.clear()
    logout_user()
    flash("Tu cuenta fue eliminada definitivamente.", "success")
    return redirect(url_for("home"))


@app.route("/perfil/recovery-codes/regenerar", methods=["POST"])
@login_required
def perfil_regenerar_recovery_codes():
    codigos_recuperacion = crear_recovery_codes(current_user.id)
    session["recovery_codes_download"] = codigos_recuperacion
    registrar_actividad(current_user.id, "recovery_codes_regenerados", "Codigos anteriores invalidados")
    db.session.commit()
    flash("Se generaron nuevos codigos. Los anteriores quedaron invalidados.", "success")
    return render_template(
        "recovery_codes.html",
        codigos=codigos_recuperacion,
        es_regeneracion=True,
    )


@app.route("/perfil/recovery-codes/descargar", methods=["POST"])
@login_required
def perfil_descargar_recovery_codes():
    codigos_recuperacion = crear_recovery_codes(current_user.id)
    registrar_actividad(current_user.id, "recovery_codes_descargados", "Codigos regenerados y descargados")
    db.session.commit()
    contenido = "Codigos de recuperacion TRIAX\n\n"
    contenido += "\n".join(codigos_recuperacion)
    contenido += "\n\nCada codigo se puede usar una sola vez. Esta descarga invalido los codigos anteriores.\n"
    return descargar_texto(f"triax-recovery-codes-{current_user.usuario}.txt", contenido)


@app.route("/perfil/trxkey/generar", methods=["POST"])
@login_required
def perfil_generar_trxkey():
    accion = request.form.get("accion", "generar")
    contenido = generar_trxkey(current_user)
    registrar_actividad(current_user.id, "trxkey_generado", "Archivo .trxkey emitido")
    db.session.commit()
    archivo = BytesIO(contenido)
    archivo.seek(0)
    nombre = f"triax-{current_user.usuario}.trxkey"
    return send_file(
        archivo,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=nombre if accion != "reemplazar" else f"triax-{current_user.usuario}-nuevo.trxkey",
    )


@app.route("/recovery-codes", methods=["GET", "POST"])
@login_required
def recovery_codes():
    if request.method == "POST":
        codigos_recuperacion = crear_recovery_codes(current_user.id)
        flash("Se generaron nuevos codigos de recuperacion. Los anteriores quedaron invalidados.", "success")
        return render_template(
            "recovery_codes.html",
            codigos=codigos_recuperacion,
            es_regeneracion=True,
        )

    codigos_disponibles = RecoveryCode.query.filter_by(
        usuario_id=current_user.id,
        usado=False,
    ).count()
    codigos_usados = RecoveryCode.query.filter_by(
        usuario_id=current_user.id,
        usado=True,
    ).count()
    return render_template(
        "recovery_codes_manage.html",
        codigos_disponibles=codigos_disponibles,
        codigos_usados=codigos_usados,
    )


@app.route("/ejecutar-ia", methods=["POST"])
@login_required
def ejecutar_ia():
    if client is None:
        return jsonify({
            "error": (
                "Falta configurar la clave de Gemini. Define la variable de entorno "
                "GEMINI_API_KEY con tu API key de Google AI Studio."
            )
        }), 500

    try:
        edad = request.form.get("edad", "").strip()
        temperatura = request.form.get("temperatura", "").strip()
        saturacion = request.form.get("saturacion", "").strip()
        presion_arterial = request.form.get("presion_arterial", "").strip()
        frecuencia_cardiaca = request.form.get("frecuencia_cardiaca", "").strip()
        dolor = request.form.get("dolor", "").strip()
        sintomas = request.form.getlist("sintomas")
        sintomas_texto = ", ".join(sintomas) if sintomas else "Sin sintomas seleccionados"
        antecedentes = request.form.getlist("antecedentes")
        antecedentes_texto = (
            ", ".join(antecedentes)
            if antecedentes
            else "Sin antecedentes medicos seleccionados"
        )
        medicamentos_riesgo = request.form.getlist("medicamentos_riesgo")
        medicamentos_riesgo_texto = (
            ", ".join(medicamentos_riesgo)
            if medicamentos_riesgo
            else "Sin medicamentos de riesgo seleccionados"
        )
        embarazada = request.form.get("embarazada", "no").strip()
        semanas_gestacion = request.form.get("semanas_gestacion", "").strip()
        movimiento_fetal = request.form.get("movimiento_fetal", "").strip()
        sintomas_obstetricos = request.form.getlist("sintomas_obstetricos")
        sintomas_obstetricos_texto = (
            ", ".join(sintomas_obstetricos)
            if sintomas_obstetricos
            else "Sin sintomas obstetricos seleccionados"
        )

        datos_obstetricos = "No aplica: paciente no embarazada."
        if embarazada == "si":
            datos_obstetricos = f"""
- Paciente embarazada: si
- Semanas de gestacion: {semanas_gestacion or "No informado"}
- Movimiento fetal: {movimiento_fetal or "No informado"}
- Sintomas obstetricos: {sintomas_obstetricos_texto}
""".strip()

        prompt_triage = f"""
Eres un asistente de apoyo para triage hospitalario en Colombia.
Clasifica el caso en nivel de triage 1 a 5 segun la urgencia clinica.

Datos del paciente:
- Edad: {edad} anos
- Temperatura: {temperatura} grados Celsius
- Saturacion SpO2: {saturacion}%
- Presion arterial: {presion_arterial}
- Frecuencia cardiaca: {frecuencia_cardiaca} lpm
- Dolor reportado: {dolor}/10
- Sintomas y alertas: {sintomas_texto}
- Antecedentes medicos: {antecedentes_texto}
- Medicamentos de riesgo: {medicamentos_riesgo_texto}

Datos obstetricos:
{datos_obstetricos}

Reglas:
- Nivel 1: atencion inmediata, riesgo vital o compromiso severo.
- Nivel 2: muy urgente, alto riesgo o deterioro posible.
- Nivel 3: urgente, requiere valoracion pronta sin compromiso vital inmediato.
- Nivel 4: menos urgente, condicion estable.
- Nivel 5: no urgente, condicion leve o administrativa.
- Tiempo maximo por nivel: nivel 1 = 0 minutos, nivel 2 = 30 minutos,
  nivel 3 = 120 minutos, nivel 4 = 240 minutos, nivel 5 = 240 minutos.
- Si hay dolor de pecho, dificultad respiratoria, convulsiones, perdida de conciencia,
  saturacion baja o signos de choque, aumenta la prioridad.
- Si el paciente presenta cardiopatia, EPOC, enfermedad renal, epilepsia o cancer,
  incrementa el nivel de vigilancia clinica.
- Si el paciente utiliza anticoagulantes, insulina, anticonvulsivos o quimioterapia,
  considera mayor riesgo de complicaciones y aumenta la prioridad cuando existan
  sintomas asociados.
- Si un paciente anticoagulado presenta sangrado, aumenta significativamente la prioridad.
- Si un paciente diabetico en tratamiento con insulina presenta alteracion de conciencia
  o mareo, aumenta la prioridad por posible complicacion metabolica.
- Si la paciente esta embarazada y presenta sangrado vaginal, convulsiones, dificultad
  respiratoria, dolor abdominal intenso, perdida de liquido amniotico, vision borrosa,
  dolor de cabeza severo, hipertension probable, movimiento fetal ausente o disminucion
  marcada de movimientos fetales, aumenta la prioridad por riesgo materno-fetal.
- No reemplazas el criterio medico; solo entregas una orientacion de apoyo.

Responde solamente un JSON valido con esta forma:
{{"nivel": 1, "prioridad": "Atencion inmediata", "justificacion": "Texto breve"}}
""".strip()

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt_triage,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        texto_limpio = (response.text or "").strip().replace("```json", "").replace("```", "")
        resultado = json.loads(texto_limpio)

        return jsonify({"respuesta": json.dumps(resultado, ensure_ascii=False)})

    except json.JSONDecodeError:
        return jsonify({"error": "Gemini respondio con un formato que no era JSON valido."}), 500
    except Exception as e:
        print(f"Error en servidor: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
