from flask import Flask, render_template, request
import sqlite3
from google import genai

app = Flask(__name__)

def get_db_connection():
    connection = sqlite3.connect("pcards.db")
    connection.row_factory = sqlite3.Row
    return connection

@app.route("/")
def home():
    return """
    <h1>P-Card Audit Website</h1>
    <p>Oklahoma State University P-Card Analysis</p>
    <h2>Part IV</h2>
    <p>Welcome to the P-Card audit website.</p>
<hr>
<nav>
    <a href="/questions">Tab 1: Ask Questions</a>
    |
    <a href="/dashboard">Tab 2: Prohibited Purchases Dashboard</a>
</nav>
    """

@app.route("/questions", methods=["GET"])
def questions():
    question = request.args.get("question", "").strip()
    connection = get_db_connection()
    cursor = connection.cursor()
    answer = ""
    question_lower = question.lower()
    if question and "how many" in question_lower and "transaction" in question_lower:
        if "2014" in question_lower:
            cursor.execute("SELECT COUNT(*) FROM pcards WHERE AgencyNumber = 1000 AND Year = 2014")    
        else:
            cursor.execute("SELECT COUNT(*) FROM pcards WHERE AgencyNumber = 1000")
        total = cursor.fetchone()[0]
        answer = "There are " + str(total) + " transactions in the database."
    elif question and "total" in question_lower and "amount" in question_lower:
        cursor.execute("SELECT SUM(Amount) FROM pcards WHERE AgencyNumber = 1000")
        total_amount = cursor.fetchone()[0]
        answer = "The total transaction amount is $" + str(round(total_amount, 2)) + "."
    elif question and "average" in question_lower and "amount" in question_lower:
        cursor.execute("SELECT AVG(Amount) FROM pcards WHERE AgencyNumber = 1000")
        average_amount = cursor.fetchone()[0]
        answer = "The average transaction amount is $" + str(round(average_amount, 2)) + "."
    elif question and "largest" in question_lower and "transaction" in question_lower:
        cursor.execute("SELECT MAX(Amount) FROM pcards WHERE AgencyNumber = 1000")
        largest_amount = cursor.fetchone()[0]
        answer = "The largest transaction amount is $" + str(round(largest_amount, 2)) + "."
    elif question:
        answer = "Sorry, I cannot answer this question yet. Please try asking about the number of transactions, total amount, average amount, or largest transaction."
    connection.close()
    return """
    <h1>Ask Questions About P-Card Transactions</h1>
    <p>Enter a question about the P-Card database.</p>
    <form>
        <input type="text" name="question"
               placeholder="Type your question here"
               size="60">
        <button type="submit">Ask</button>
    </form>
    <p><a href="/">Back to Home</a></p>
     """ + "<h3>Answer</h3><p>" + answer + "</p>"

@app.route("/dashboard")
def dashboard():
    year = request.args.get("year", "")
    description = request.args.get("description", "").strip()
    vendor = request.args.get("vendor", "").strip()
    connection = get_db_connection()
    cursor = connection.cursor()
    query = "SELECT * FROM pcards WHERE AgencyNumber = 1000"
    parameters = []
    if year:
        query += " AND Year = ?"
        parameters.append(year)
    if description:
        query += " AND Description LIKE ?"
        parameters.append("%" + description + "%")
    if vendor:
        query += " AND Vendor LIKE ?"
        parameters.append("%" + vendor + "%")
    count_query = query.replace("SELECT *", "SELECT COUNT(*)", 1)
    cursor.execute(count_query, parameters)
    total_matches = cursor.fetchone()[0]
    query += " LIMIT 100"
    cursor.execute(query, parameters)
    transactions = cursor.fetchall()
    connection.close()
    results_html = "<h3>Search Results</h3>"
    results_html += "<p>Matching transactions: " + str(total_matches) + " (showing first 100)</p>"
    results_html += "<table border='1' cellpadding='5'>"
    results_html += "<tr><th>Year</th><th>Date</th><th>Agency</th><th>Cardholder</th><th>Description</th><th>Vendor</th><th>Amount</th></tr>"
    for transaction in transactions:
        results_html += "<tr>"
        for column in ["Year", "TransactionDate", "AgencyName", "FullName", "Description", "Vendor", "Amount"]:
            results_html += "<td>" + str(transaction[column] or "") + "</td>"
        results_html += "</tr>"

    results_html += "</table>"
    return """
    <h1>Prohibited Purchases Dashboard</h1>
    <p>Search P-Card transactions for possible prohibited purchases.</p>
<h3>Select Year</h3>
<form action="/dashboard" method="GET">
    <label for="year">Choose a year:</label>
    <select name="year" id="year">
        <option value="">All Years</option>
        <option value="2014" selected>2014</option>
    </select>
    <button type="submit">Search</button>
</form>
<h3>Description Search</h3>
<p>Enter a keyword to find possible prohibited purchases, such as alcohol.</p>

<form action="/dashboard" method="GET">
<input type="hidden" name="year" value="" id="description_year">
<script>
document.getElementById("description_year").value = document.getElementById("year").value;
</script>
    <label for="description">Description keyword:</label>
    <input type="text" id="description" name="description"
           placeholder="e.g. alcohol">
    <button type="submit" onclick="document.getElementById('description_year').value = document.getElementById('year').value;">Search Description</button>
</form>
<h3>Vendor Search</h3>
<p>Enter a vendor keyword, such as post office, to find possible prohibited purchases.</p>

<form action="/dashboard" method="GET">
<input type="hidden" name="year" value="" id="vendor_year">
    <label for="vendor">Vendor keyword:</label>
    <input type="text" id="vendor" name="vendor"
           placeholder="e.g. post office">
    <button type="submit" onclick="document.getElementById('vendor_year').value = document.getElementById('year').value;">Search Vendor</button>
</form>
        """ + results_html + '<p><a href="/">Back to Home</a></p>'
