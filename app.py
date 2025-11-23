from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_migrate import Migrate
from models import db, User, Client, Project, Service, Industry
from datetime import datetime, date
from sqlalchemy import func
import click
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:4780@db/integrator_db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "supersecretkey"

db.init_app(app)
migrate = Migrate(app, db)


def is_admin():
    return session.get("is_admin", False)


def parse_date_safe(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# --- CLI-команды ---

@app.cli.command("init-db")
def init_db():
    """Создать таблицы без Alembic (разово)."""
    db.create_all()
    click.echo("✅ Таблицы созданы")


@app.cli.command("create-admin")
@click.option("--username", "-u", default="admin")
@click.option("--password", "-p", default="admin123")
def create_admin(username, password):
    """Создать администратора, если его нет."""
    with app.app_context():
        admin = User.query.filter_by(username=username).first()
        if admin:
            click.echo("⚠️ Админ уже существует")
            return
        admin = User(username=username, is_admin=True, qualification="expert")
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"✅ Админ создан: {username}/{password}")


@app.cli.command("seed-data")
def seed_data():
    """Создать базовые сферы и сотрудников-специалистов."""
    with app.app_context():
        industry_names = [
            "Банковский сектор",
            "Госструктуры",
            "ИТ-компании",
            "Промышленность",
            "Ритейл",
        ]
        industries_map = {}
        for name in industry_names:
            ind = Industry.query.filter_by(name=name).first()
            if not ind:
                ind = Industry(name=name)
                db.session.add(ind)
            industries_map[name] = ind

        db.session.flush()

        employees = [
            ("ivan_sec", "123", "middle", ["Банковский сектор", "ИТ-компании"]),
            ("petr_gov", "123", "senior", ["Госструктуры"]),
            ("olga_ind", "123", "junior", ["Промышленность"]),
            ("dmitry_rt", "123", "expert", ["Ритейл", "Банковский сектор"]),
        ]

        for username, pwd, qual, specs in employees:
            user = User.query.filter_by(username=username).first()
            if user:
                continue
            user = User(username=username, qualification=qual, is_admin=False)
            user.set_password(pwd)
            user.industries = [industries_map[s] for s in specs]
            db.session.add(user)

        db.session.commit()
        click.echo("✅ Базовые сферы и сотрудники созданы")


# --- маршруты аутентификации ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    industries = Industry.query.order_by(Industry.name).all()

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Заполните логин и пароль", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Имя пользователя уже занято", "danger")
            return redirect(url_for("register"))

        user = User(username=username)  # qualification по умолчанию = junior
        user.set_password(password)

        industry_ids = request.form.getlist("industry_ids")
        if industry_ids:
            inds = Industry.query.filter(Industry.id.in_(industry_ids)).all()
            user.industries = inds

        db.session.add(user)
        db.session.commit()
        flash("Регистрация успешна!", "success")
        return redirect(url_for("login"))

    return render_template("register.html", industries=industries)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["is_admin"] = user.is_admin
            flash("Вы вошли!", "success")
            return redirect(url_for("dashboard"))
        flash("Неверный логин или пароль", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли", "info")
    return redirect(url_for("login"))


# --- дашборд ---

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Войдите в аккаунт", "warning")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = db.session.get(User, user_id)

    if session.get("is_admin"):
        clients = Client.query.all()
        return render_template("dashboard.html", user=user, clients=clients, is_admin=True)
    else:
        projects = Project.query.filter_by(user_id=user_id).all()
        client_ids = list({p.client_id for p in projects})
        clients = Client.query.filter(Client.id.in_(client_ids)).all()
        return render_template("dashboard.html", user=user, clients=clients, is_admin=False)


# --- клиенты ---

@app.route("/clients")
def list_clients():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if session.get("is_admin"):
        clients = Client.query.all()
    else:
        user_projects = Project.query.filter_by(user_id=session["user_id"]).all()
        client_ids = list({p.client_id for p in user_projects})
        clients = Client.query.filter(Client.id.in_(client_ids)).all()

    return render_template("clients.html", clients=clients)


@app.route("/clients/add", methods=["GET", "POST"])
def add_client():
    if not is_admin():
        flash("Доступ только для администратора", "danger")
        return redirect(url_for("list_clients"))

    industries = Industry.query.order_by(Industry.name).all()

    if request.method == "POST":
        name = request.form["name"].strip()

        existing = Client.query.filter(func.lower(Client.name) == func.lower(name)).first()
        if existing:
            flash("Организация с таким названием уже существует", "danger")
            return redirect(url_for("add_client"))

        industry_id = request.form.get("industry_id")
        if not industry_id:
            flash("Выберите сферу деятельности", "danger")
            return redirect(url_for("add_client"))

        client = Client(
            name=name,
            contact_name=request.form["contact_name"],
            phone=request.form["phone"],
            email=request.form["email"],
            industry_id=int(industry_id),
            user_id=session.get("user_id"),
        )
        db.session.add(client)
        db.session.commit()
        flash("Клиент добавлен", "success")
        return redirect(url_for("list_clients"))

    return render_template("add_client.html", industries=industries)


@app.route("/clients/<int:client_id>/edit", methods=["POST"])
def edit_client(client_id):
    if not session.get("is_admin"):
        flash("Доступ запрещён", "danger")
        return redirect(url_for("list_clients"))

    client = Client.query.get_or_404(client_id)
    client.name = request.form["name"]
    client.contact_name = request.form["contact_name"]
    client.phone = request.form["phone"]
    client.email = request.form["email"]

    industry_id = request.form.get("industry_id")
    if industry_id:
        client.industry_id = int(industry_id)

    db.session.commit()
    flash("Клиент обновлён", "success")
    return redirect(url_for("list_clients"))


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    if not session.get("is_admin"):
        flash("Доступ запрещён", "danger")
        return redirect(url_for("list_clients"))

    client = Client.query.get_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    flash("Клиент удалён", "info")
    return redirect(url_for("list_clients"))


# --- проекты ---

@app.route("/projects/<int:client_id>")
def list_projects(client_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    client = Client.query.get_or_404(client_id)

    if not is_admin():
        allowed = Project.query.filter_by(client_id=client.id, user_id=session["user_id"]).count()
        if allowed == 0:
            flash("Нет доступа к этому клиенту", "danger")
            return redirect(url_for("dashboard"))

    status_filter = request.args.get("status")
    if status_filter:
        projects = Project.query.filter_by(client_id=client.id, status=status_filter).all()
    else:
        projects = client.projects

    return render_template("projects.html", client=client, projects=projects, status_filter=status_filter)


@app.route("/projects/add/<int:client_id>", methods=["GET", "POST"])
def add_project(client_id):
    if not is_admin():
        flash("Только администратор может добавлять проекты", "danger")
        return redirect(url_for("dashboard"))

    client = Client.query.get_or_404(client_id)

    if client.industry_id:
        eligible_users = (
            User.query
            .join(User.industries)
            .filter(Industry.id == client.industry_id)
            .all()
        )
    else:
        eligible_users = []

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        start_date = parse_date_safe(request.form.get("start_date"))
        end_date = parse_date_safe(request.form.get("end_date"))
        user_id = request.form.get("user_id")

        if not name or not start_date or not user_id:
            flash("Пожалуйста, заполните все обязательные поля корректно", "danger")
            return redirect(request.url)

        assigned_user = User.query.get(int(user_id))
        if assigned_user not in eligible_users:
            flash("Этот сотрудник не специализируется на сфере данного клиента", "danger")
            return redirect(request.url)

        if end_date and end_date < start_date:
            flash("Дата окончания не может быть раньше даты начала", "danger")
            return redirect(request.url)

        project = Project(
            name=name,
            status="активный",
            start_date=start_date,
            end_date=end_date,
            client_id=client_id,
            user_id=int(user_id),
        )

        db.session.add(project)
        db.session.commit()
        flash("Проект добавлен", "success")
        return redirect(url_for("list_projects", client_id=client_id))

    if not eligible_users:
        flash("Для сферы этого клиента пока нет подходящих сотрудников", "warning")

    return render_template(
        "add_project.html",
        client_id=client_id,
        client=client,
        users=eligible_users,
        current_date=date.today().isoformat(),
    )


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    if not is_admin():
        flash("Удаление проекта доступно только администратору", "danger")
        return redirect(url_for("dashboard"))

    project = Project.query.get_or_404(project_id)
    client_id = project.client_id

    Service.query.filter_by(project_id=project_id).delete()

    db.session.delete(project)
    db.session.commit()
    flash("Проект удалён", "info")
    return redirect(url_for("list_projects", client_id=client_id))


@app.route("/projects/<int:project_id>/complete", methods=["POST"])
def complete_project(project_id):
    project = Project.query.get_or_404(project_id)

    if not is_admin() and project.user_id != session.get("user_id"):
        flash("Нет прав завершить проект", "danger")
        return redirect(url_for("dashboard"))

    if any(service.status != "завершена" for service in project.services):
        flash("Нельзя завершить проект — не все услуги завершены", "warning")
        return redirect(url_for("list_services", project_id=project.id))

    project.status = "завершён"
    db.session.commit()
    flash("Проект успешно завершён!", "success")
    return redirect(url_for("list_services", project_id=project.id))


# --- услуги ---

@app.route("/services/<int:project_id>")
def list_services(project_id):
    db.session.expire_all()
    project = Project.query.get_or_404(project_id)
    return render_template("services.html", project=project, services=project.services)


@app.route("/services/add/<int:project_id>", methods=["GET", "POST"])
def add_service(project_id):
    project = Project.query.get_or_404(project_id)

    if not is_admin() and project.user_id != session["user_id"]:
        flash("Нет доступа к добавлению услуги", "danger")
        return redirect(url_for("dashboard"))

    if project.status == "завершён":
        flash("Невозможно добавить услугу в завершённый проект.", "danger")
        return redirect(url_for("list_services", project_id=project.id))

    if request.method == "POST":
        execution_date = datetime.strptime(request.form["execution_date"], "%Y-%m-%d").date()

        if project.end_date and execution_date > project.end_date:
            flash("Дата услуги не может быть позже даты окончания проекта", "danger")
            return redirect(url_for("add_service", project_id=project.id))

        service = Service(
            service_type=request.form["service_type"],
            status="в процессе",
            execution_date=execution_date,
            project_id=project.id,
        )
        db.session.add(service)
        db.session.commit()
        flash("Услуга добавлена", "success")
        return redirect(url_for("list_services", project_id=project.id))

    return render_template("add_service.html", project_id=project_id, project=project,
                           current_date=date.today().isoformat())


@app.route("/services/complete/<int:service_id>", methods=["POST"])
def complete_service(service_id):
    service = Service.query.get_or_404(service_id)
    project = service.project

    if not is_admin() and project.user_id != session["user_id"]:
        flash("Нет прав завершить услугу", "danger")
        return redirect(url_for("dashboard"))

    service.status = "завершена"
    db.session.commit()
    flash("Услуга завершена", "success")
    return redirect(url_for("list_services", project_id=project.id))


@app.route("/services/<int:service_id>/delete", methods=["POST"])
def delete_service(service_id):
    service = Service.query.get_or_404(service_id)

    if not is_admin():
        flash("Удаление услуги доступно только администратору", "danger")
        return redirect(url_for("dashboard"))

    project_id = service.project_id
    db.session.delete(service)
    db.session.commit()
    flash("Услуга удалена", "info")
    return redirect(url_for("list_services", project_id=project_id))


# --- сотрудники ---

@app.route("/employees")
def list_employees():
    if not is_admin():
        flash("Доступ только для администратора", "danger")
        return redirect(url_for("dashboard"))

    filter_param = request.args.get("filter")
    all_users = User.query.all()

    if filter_param == "empty":
        employees = [u for u in all_users if len(u.projects) == 0]
    elif filter_param == "active":
        employees = [u for u in all_users if any(p.status != 'завершён' for p in u.projects)]
        # иначе все
    else:
        employees = all_users

    return render_template("employees.html", employees=employees, filter=filter_param, is_admin=True)


@app.route("/employees/<int:user_id>/specializations", methods=["GET", "POST"])
def edit_employee_specializations(user_id):
    if not is_admin():
        flash("Доступ запрещён", "danger")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)
    all_industries = Industry.query.order_by(Industry.name).all()

    if request.method == "POST":
        industry_ids = request.form.getlist("industry_ids")
        if industry_ids:
            new_inds = Industry.query.filter(Industry.id.in_(industry_ids)).all()
            user.industries = new_inds
        else:
            user.industries = []

        db.session.commit()
        flash("Специализации сотрудника обновлены", "success")
        return redirect(url_for("list_employees"))

    return render_template("edit_employee_specializations.html", employee=user, industries=all_industries)


@app.route("/employees/<int:user_id>/delete", methods=["POST"])
def delete_employee(user_id):
    if not is_admin():
        flash("Доступ запрещён", "danger")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)

    if user.id == session.get("user_id"):
        flash("Нельзя удалить самого себя", "warning")
        return redirect(url_for("list_employees"))

    if user.is_admin:
        flash("Нельзя удалить администратора", "warning")
        return redirect(url_for("list_employees"))

    active_projects = Project.query.filter_by(user_id=user.id).filter(Project.status != 'завершён').count()
    if active_projects > 0:
        flash("Нельзя удалить сотрудника с незавершёнными проектами", "warning")
        return redirect(url_for("list_employees"))

    Project.query.filter_by(user_id=user.id).delete()

    db.session.delete(user)
    db.session.commit()
    flash("Сотрудник удалён", "info")
    return redirect(url_for("list_employees"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
