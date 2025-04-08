import streamlit as st
import mysql.connector
from mysql.connector import Error
from PyPDF2 import PdfReader
import uuid
import google.generativeai as genai
import re

import os 
from dotenv import load_dotenv
load_dotenv()

api_key=os.getenv("GEMINI_API")
# Configure Gemini
genai.configure(api_key=api_key)  # Replace with your API key
model = genai.GenerativeModel("gemini-1.5-flash")

# Database configuration
db_config = {
    'host': '127.0.0.1',
    'user': 'enspirit',
    'password': 'enspirit123',
    'database': 'pdfchatbot'
}

# PDF extraction function
def extract_data_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        content = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                content.append(text.strip())
        full_text = " ".join(content)
        return re.sub(r'\s+', ' ', full_text).strip()
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return ""

# Save user and assistant chat to database
def save_chat_to_db(user_id, user_chat, assistant_chat):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        chat_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO chathistory (chat_id, user_id, user_chat, assistant_chat)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, user_id, user_chat, assistant_chat))
        conn.commit()
    except Error as e:
        st.error(f"DB Error: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Get or create user
def get_or_create_user(name):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_name = %s", (name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            user_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO users (user_id, user_name) VALUES (%s, %s)", (user_id, name))
            conn.commit()
            return user_id
    except Error as e:
        st.error(f"Error with user DB: {e}")
        return None
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Generate assistant response
def generate_gemini_response(context, question):
    try:
        prompt = f"""You are a helpful assistant. Answer the question based only on the context below.
If the answer is not found in the context, respond with "not found".

Context:
{context}

Question: {question}
Answer:"""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error: {str(e)}"
    

def get_db_connection():
    """Returns a new MySQL database connection."""
    return mysql.connector.connect(
        host="127.0.0.1",
        user=os.getenv("DB_USER", "enspirit"),  
        password=os.getenv("DB_PASS", "enspirit123"),
        database=os.getenv("DB_NAME", "pdfchatbot")  # Ensure this matches your actual DB name
    )

def create_db_and_tables():
    conn = None
    cursor = None
    try:
        # Establish database connection
        conn = mysql.connector.connect(
            host="127.0.0.1",
            user="enspirit",
            password="enspirit123"
        )

        cursor = conn.cursor()

        # Create the database if it doesn't exist
        cursor.execute("CREATE DATABASE IF NOT EXISTS pdfchatbot")
        cursor.execute("USE pdfchatbot")

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE
            )
        """)

        # Create chathistory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chathistory (
                chat_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                user_chat TEXT,
                assistant_chat TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        print("✅ Database and tables created successfully.")
    
    except Error as e:
        print(f"❌ Error: {e}")

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def logout():
    for key in st.session_state.keys():
        del st.session_state[key]
    st.rerun()


# Fetch and display chat history for the current user
def display_chat_history(user_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_chat, assistant_chat
            FROM chathistory
            WHERE user_id = %s
            ORDER BY created_at ASC
        """, (user_id,))
        chats = cursor.fetchall()

        if chats:
            with st.sidebar:
                st.markdown("## 💬 Chat History")
                for user_chat, assistant_chat in reversed(chats):
                    st.markdown("**👤 You:**")
                    st.write(user_chat)

                    st.markdown("**🤖 Bot:**")
                    st.write(assistant_chat)
                    st.markdown("---")
        else:
            with st.sidebar:
                st.info("No previous chat history found.")
    except Error as e:
        st.sidebar.error(f"Error fetching chat history: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()



st.set_page_config("PDF Q&A Chatbot")
st.title("📄 PDF Q&A Chatbot")


# Top-right logout button
col1, col2, col3 = st.columns([6, 1, 1])
with col3:
    if st.button("🚪 Logout"):
        logout()


if "user_id" not in st.session_state:
    name = st.text_input("Enter your name to begin:")

    if st.button("login"):
        # Create tables and fetch/create user
        create_db_and_tables()
        st.session_state.user_id = get_or_create_user(name)
        st.rerun()

else:
    # Only run this once after login
    if "history_loaded" not in st.session_state:
        display_chat_history(st.session_state.user_id)
        st.session_state.history_loaded = True

    # Upload PDF
    uploaded_file = st.file_uploader("Upload a PDF", type="pdf")

    if uploaded_file:
        pdf_text = extract_data_from_pdf(uploaded_file)
        st.session_state.pdf_text = pdf_text
        st.success("PDF uploaded and processed!")

    # Chat input
    if "pdf_text" in st.session_state:
        user_question = st.chat_input("Ask a question about the PDF")
        display_chat_history(st.session_state.user_id)
        if user_question:
            with st.spinner("Thinking..."):
                answer = generate_gemini_response(st.session_state.pdf_text, user_question)

                # Show in main UI
                st.chat_message("user").markdown(user_question)
                st.chat_message("assistant").markdown(answer)

                # Save to DB
                save_chat_to_db(st.session_state.user_id, user_question, answer)

                # Instantly refresh sidebar with updated history
                display_chat_history(st.session_state.user_id)


