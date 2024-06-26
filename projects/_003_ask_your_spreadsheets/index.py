import streamlit as st
import pandas as pd
import sqlite3
from projects._003_ask_your_spreadsheets.gpt_api_calls import generate_sql_statement
from mixpanel import Mixpanel
mp = Mixpanel(st.secrets["mixpanel"]["token"])

def project_header():
    st.title('📈 Ask Your Database')
    st.write("Upload your databases (as CSV files), and ask questions in plain english. This program will auto-generate and execute SQL queries to retrieve the data needed to answer your question. It can also generate question ideas to help you get the most business insight from your data.")

def project_details():
    project_header()
    with st.expander("✨ See project details"):
        st.subheader("Why I built this")
        st.write("One of the founders at my co-working space said one of their biggest pain points for their data business was being able to answer complex questions about their industry based on the data because 1) The data was spread across multiple spreadsheets and was difficult to find, and 2) Writing queries to retrieve data based on complex questions required time and expertise. I thought that GenAI could be used to solve this.")
        st.subheader("Demo video")
        st.video("demo_videos/ask_your_spreadsheets_demo.mp4")
        st.warning("I initially planned to let people connect to their own database, like MySQL/PostgreSQL by entering their database connection details, but decided against this for security reasons.")
        st.subheader("Ways to use this")
        st.markdown("- 🩺 **Healthcare Data**: Anonymised data around patient records, treatment details, and outcomes data. This would allow for queries like, 'Show the average recovery time for patients aged 60-70 with a specific condition,' or create questions such as, 'Which treatments have the highest success rate for chronic diseases?'")
        st.markdown("- 🏘️ **Real-estate Market Trends**:  Use datasets on property sales, prices, demographics, and economic indicators. This can help answer questions like, 'What is the average price of three-bedroom houses in a specific area?' or generate queries like, 'What factors most significantly affect property values in urban areas?'")
        st.markdown("- 🌳 **Environmental Data Analysis**: Use datasets related to climate, pollution levels, or wildlife populations. This might answer queries like, 'What has been the average air quality index in urban areas over the past five years?' and generate questions like, 'What is the correlation between temperature changes and wildlife migration patterns?'")
        st.markdown("- 🚂 **Transportation and Logistics**: Work with data related to public transportation usage, traffic patterns, and logistic operations. This can help in answering questions such as, 'What are the peak hours for public transportation usage in major cities?' or suggest questions like, 'How do weather conditions affect transportation delays?'")
        st.subheader("Limitations")
        st.error('⚠️ **CSV format only**: I initially planned to let people connect to their own database, like MySQL/PostgreSQL by entering their database connection details, but decided against this for security reasons, so you have to export your databases to CSV files and upload each time you want to ask questions.')
        st.error("⚠️ **Accuracy**: SQL statements are not always correct, and can struggle with very complex queries involving 2+ datasets.")
        st.write("")

def csv_file_viewer(dataframes):
    project_header()
    with st.expander("📊 View Uploaded CSV Files"):
        selected_file = st.selectbox("Choose a File to View:", list(dataframes.keys()))
        if selected_file:
            st.dataframe(dataframes[selected_file])

@st.cache_resource
def get_sql_connection():
    return sqlite3.connect(':memory:')

def drop_all_tables(conn):
    """Drop all tables in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table_name in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name[0]}")
    conn.commit()

def get_table_schemas_with_data(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    table_names = cursor.fetchall()
    schemas_with_data = ""

    for table_name in table_names:
        cursor.execute(f"PRAGMA table_info('{table_name[0]}')")
        columns = cursor.fetchall()
        table_schemas = f"CREATE TABLE {table_name[0]} (\n"
        data_query = f"SELECT * FROM {table_name[0]} LIMIT 1;"
        cursor.execute(data_query)
        first_row_data = cursor.fetchone()

        for column in columns:
            column_name = column[1].replace(' ', '_')
            column_type = column[2]
            # Exclude long text content by checking column type
            if "text" not in column_type.lower():
                table_schemas += f"    {column_name} {column_type},\n"

        table_schemas = table_schemas.rstrip(",\n") + "\n);\n\n"
        table_schemas += f"First Row Data: {first_row_data}\n\n"
        schemas_with_data += table_schemas

    return schemas_with_data

def execute_sql_statement(conn, sql_statement):
    rows_returned = False
    try:
        result = pd.read_sql_query(sql_statement, conn)
        if not result.empty:
            rows_returned = True
    except Exception as e:
        pass
    finally:
        mp.track(st.session_state['session_id'], "Run SQL Query", {
            "Rows Returned": rows_returned,
            'Page Name': 'Ask Your Database'
        })

    return result if rows_returned else None

def step_1():
    st.title("Step 1/2: Upload CSV Files")
    uploaded_files = st.file_uploader("Upload CSV Files", type=["csv"], accept_multiple_files=True)

    # Create a temporary state variable to track the upload completion
    if 'upload_completed' not in st.session_state:
        st.session_state.upload_completed = False

    if uploaded_files:
        conn = get_sql_connection()
        drop_all_tables(conn)
        dataframes = {}

        for file in uploaded_files:
            df = pd.read_csv(file)
            df.columns = [col.replace(' ', '_') for col in df.columns]
            table_name = file.name.split('.')[0]
            dataframes[file.name] = df
            df.to_sql(table_name, conn, index=False)

        st.session_state['conn'] = conn
        st.session_state['dataframes'] = dataframes
        st.session_state.upload_completed = True

    if st.button("Finished Uploading Data") or st.session_state.upload_completed:
        if 'dataframes' in st.session_state and st.session_state['dataframes']:
            mp.track(st.session_state['session_id'], "Upload CSV files", {
                "Number of CSV files uploaded": len(st.session_state['dataframes']),
                'Page Name': 'Ask Your Database'
            })
            st.session_state.step = 2
            st.session_state.upload_completed = False
        else:
            st.warning("Please upload at least one CSV file to proceed.")

def step_2():
    st.title("Step 2/2: Ask a Question")

    question = st.text_area("Question:", value="Show me everything in X table")
    if st.button("Ask Question"):
        api_key = st.session_state.get('api_key', '')

        if not api_key:
            st.error("🔐  Please enter an OpenAI API key in the sidebar to proceed.")
            return
        conn = st.session_state['conn']
        table_schemas = get_table_schemas_with_data(conn)
        sql_statement = generate_sql_statement(question, table_schemas)

        if sql_statement:
            st.write("Generated SQL Query:")
            st.code(sql_statement, language='sql')

            result_df = execute_sql_statement(conn, sql_statement)

            if result_df is not None and not result_df.empty:
                st.write("Results:")
                st.dataframe(result_df)
            else:
                st.info("No results or unable to execute the query.")
        else:
            st.warning("Failed to generate SQL statement.")

def ask_your_spreadsheets():
    if 'step' not in st.session_state:
        st.session_state.step = 1

    if st.session_state.step == 1:
        project_details()
        step_1()
    elif st.session_state.step == 2:
        csv_file_viewer(st.session_state['dataframes'])
        step_2()