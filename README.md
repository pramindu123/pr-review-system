# GitHub PR Review System

A Django-based tool that automatically reviews GitHub Pull Requests, generates structured feedback, and routes it to instructors for approval.

## Features

- **Automatic PR Reviews**: Automatically fetches and reviews PRs from connected GitHub repositories
- **Branch-Based Expectations**: Different review standards based on branch naming conventions (feature/, bugfix/, hotfix/, etc.)
- **Instructor Approval Workflow**: Reviews are routed to instructors for approval before being finalized
- **GitHub Integration**: Posts approved feedback directly to GitHub PRs
- **Dashboard Interface**: Clean UI for managing repositories, viewing PRs, and handling approvals

## Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
GITHUB_TOKEN=your-github-personal-access-token
GITHUB_WEBHOOK_SECRET=your-webhook-secret
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Run Development Server

```bash
python manage.py runserver
```

Visit `http://localhost:8000` to access the application.

## Branch Naming Conventions

The system recognizes the following branch patterns and applies different review expectations:

| Branch Pattern | Review Focus |
|---------------|--------------|
| `feature/*` | New functionality, tests, documentation |
| `bugfix/*` | Bug fixes, regression tests |
| `hotfix/*` | Critical fixes, minimal changes |
| `release/*` | Version bumps, changelog updates |
| `refactor/*` | Code quality, no behavior changes |

## API Endpoints

- `GET /api/repositories/` - List connected repositories
- `POST /api/repositories/` - Add a new repository
- `GET /api/pull-requests/` - List all pull requests
- `GET /api/pull-requests/<id>/` - Get PR details
- `POST /api/pull-requests/<id>/review/` - Trigger manual review
- `GET /api/reviews/` - List all reviews
- `POST /api/reviews/<id>/approve/` - Approve a review
- `POST /api/reviews/<id>/reject/` - Reject a review
- `GET /api/branch-rules/` - List branch rules
- `POST /api/webhooks/github/` - GitHub webhook endpoint

## Architecture

```
pr_review_system/
├── settings.py          # Django settings
├── urls.py              # Root URL configuration
└── wsgi.py              # WSGI config

reviews/
├── models.py            # Database models
├── views.py             # API views
├── serializers.py       # DRF serializers
├── github_client.py     # GitHub API integration
├── review_engine.py     # PR review logic
├── urls.py              # App URL routes
└── templates/           # Frontend templates
```

## License

MIT License
