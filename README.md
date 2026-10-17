# Insurance ensurance flask program 

## Dependencies
install dependencies for flask from requirements.txt file with

`pip install -r requirements.txt`

for a separate virtual environment:

```
python -m venv .venv
chmod +x .venv/bin/activate
source .venv/bin/activate
```

## Run the app
%% usually port 5000 %%

`python app.py`

### Example requests for endpoints

`curl -X "GET" http://localhost:5000/health`
`curl -X "POST" -F "file=@contract.pdf" http://127.0.0.1:5000/api/contracts`
