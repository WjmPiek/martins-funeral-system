param([string]$Message = "schema update")
$env:FLASK_APP = "run.py"
flask db migrate -m $Message
flask db upgrade
