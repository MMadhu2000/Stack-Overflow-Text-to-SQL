import streamlit as st
import re
from langchain_community.utilities import SQLDatabase
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

st.set_page_config(
    page_title="Stack Overflow Text-to-SQL",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp {
        background-color: #0f1117;
        color: #e6e6e6;
    }
    h1, h2, h3 {
        color: #f0f0f0 !important;
        font-weight: 600;
    }
    .stTextInput > div > div > input {
        background-color: #1c1f26;
        color: #e6e6e6;
        border: 1px solid #2e3440;
        border-radius: 8px;
    }
    .stButton > button {
        background-color: #3b82f6;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.2rem;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: #2563eb;
    }
    .stCodeBlock {
        background-color: #1c1f26 !important;
        border-radius: 8px;
    }
    .result-box {
        background-color: #1c1f26;
        border: 1px solid #2e3440;
        border-radius: 8px;
        padding: 1rem;
        margin-top: 1rem;
    }
    .footer {
        margin-top: 3rem;
        text-align: center;
        color: #6b7280;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("Stack Overflow Text-to-SQL")
st.markdown("Ask questions about live Stack Overflow data stored locally.")

@st.cache_resource
def get_database():
    return SQLDatabase.from_uri("sqlite:///stackoverflow.db")

@st.cache_resource
def get_llm():
    return ChatOllama(model="llama3", temperature=0)

db = get_database()
llm = get_llm()
schema = db.get_table_info()

prompt = ChatPromptTemplate.from_template("""
You are a senior SQL expert working with a Stack Overflow database.

Given the database schema below, write a correct SQLite query that answers the user's question.

Rules:
- Use only the tables and columns present in the schema
- Return ONLY the SQL query
- Do not explain anything
- Do not wrap the query in markdown
- Prefer simple and readable SQL

Schema:
{schema}

Question:
{question}
""")

sql_chain = prompt | llm | StrOutputParser()

FORBIDDEN_KEYWORDS = [
    r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
    r"\bALTER\b", r"\bCREATE\b", r"\bTRUNCATE\b", r"\bREPLACE\b",
    r"\bATTACH\b", r"\bDETACH\b", r"\bPRAGMA\b"
]

def is_safe_query(query: str) -> bool:
    query_upper = query.upper()
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, query_upper):
            return False
    return True

question = st.text_input(
    "Your question",
    placeholder="Example: Which users have the highest reputation?"
)

if st.button("Run Query"):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Generating SQL..."):
            try:
                raw_sql = sql_chain.invoke({
                    "schema": schema,
                    "question": question
                }).strip()

                sql_query = raw_sql.replace("```sql", "").replace("```", "").strip()

                st.subheader("Generated SQL")
                st.code(sql_query, language="sql")

                if not is_safe_query(sql_query):
                    st.error("This query was blocked by safety guardrails. Only SELECT queries are allowed.")
                else:
                    result = db.run(sql_query)
                    st.subheader("Result")
                    st.markdown(f'<div class="result-box">{result}</div>', unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Error: {str(e)}")

st.markdown('<div class="footer">Local model: Ollama Llama 3.2:1b | Live data from Stack Exchange API</div>', unsafe_allow_html=True)