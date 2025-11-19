
import streamlit as st
import os
from openai import AzureOpenAI
from dotenv import load_dotenv
load_dotenv()

def main():
    MODEL = "gpt-4o"

    client = AzureOpenAI(
        api_key         = os.environ["AZURE_OPENAI_API_KEY"],
        api_version     = os.environ["OPENAI_API_VERSION"],
        azure_endpoint  = os.environ["OPENAI_API_VERSION"],
    )


    # The title method is used to display a text with big bold font at the page:
    st.title("DIAL API Demo")

    # The caption method is used to display a small text below the title:
    st.caption("Streamlit application using DIAL API demo")

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "system", "content": "You are a helpful assistant."}]


    for message in st.session_state.messages:
        if message["role"] == "system":
            continue  # Skip displaying system messages
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("How can I help you?")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        response = client.chat.completions.create(
            model    = MODEL,
            messages = st.session_state.messages
        )
        assistant_replied = (response.choices[0].message.content)
        st.session_state.messages.append({"role": "assistant", "content": assistant_replied})
        with st.chat_message("assistant"):
            st.markdown(assistant_replied)

if __name__ == "__main__":
    main()
