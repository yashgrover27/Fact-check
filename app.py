import streamlit as st
import PyPDF2
from mistralai import Mistral
from tavily import TavilyClient
import json
import io
from typing import List, Dict

# Page configuration
st.set_page_config(
    page_title="PDF Fact Checker",
    page_icon="📄",
    layout="wide"
)

# Title and description
st.title("📄 PDF Fact Checker")
st.markdown("""
Upload a PDF document and this tool will extract claims and fact-check them using real-time web search.
Powered by Mistral AI and Tavily Search.
""")

# Sidebar for API keys
with st.sidebar:
    st.header("⚙️ Configuration")
    mistral_api_key = "9LFYiwWSYI3FgSzv5PP4YJWZlGsRcUgF"
    tavily_api_key = "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"
    
    st.markdown("---")
    st.markdown("### About")
    st.markdown("""
    This tool:
    1. Extracts text from your PDF
    2. Identifies key claims using Mistral AI
    3. Fact-checks each claim using Tavily search
    4. Presents a detailed analysis
    """)

def extract_text_from_pdf(pdf_file) -> str:
    """Extract text content from uploaded PDF file."""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        st.error(f"Error extracting PDF text: {str(e)}")
        return ""

def extract_claims(mistral_client: Mistral, document_text: str) -> List[Dict]:
    """Use Mistral to extract factual claims from the document."""
    prompt = f"""Analyze the following document and extract all specific factual claims that can be verified.

For each claim, provide:
1. The claim itself (be specific and concise)
2. The category (e.g., "Cryptocurrency", "AI", "Economy", "Technology", etc.)
3. A search query to verify this claim

Return ONLY a valid JSON array of objects with keys: "claim", "category", "search_query"

Document:
{document_text}

JSON Response:"""

    try:
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        
        # Try to parse the response
        try:
            result = json.loads(content)
            # Handle different JSON structures
            if isinstance(result, dict):
                if 'claims' in result:
                    return result['claims']
                elif 'data' in result:
                    return result['data']
                else:
                    # If it's a dict but not the expected structure, wrap it
                    return [result]
            elif isinstance(result, list):
                return result
            else:
                st.error("Unexpected response format from Mistral")
                return []
        except json.JSONDecodeError:
            st.error("Failed to parse Mistral response as JSON")
            st.code(content)
            return []
            
    except Exception as e:
        st.error(f"Error extracting claims with Mistral: {str(e)}")
        return []

def fact_check_claim(tavily_client: TavilyClient, claim: str, search_query: str) -> Dict:
    """Use Tavily to search for information to verify the claim."""
    try:
        search_results = tavily_client.search(
            query=search_query,
            max_results=5,
            search_depth="advanced"
        )
        
        return {
            "success": True,
            "results": search_results.get('results', []),
            "answer": search_results.get('answer', '')
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "answer": ""
        }

def analyze_claim_with_mistral(mistral_client: Mistral, claim: str, search_results: List[Dict]) -> Dict:
    """Use Mistral to analyze if the claim is accurate based on search results."""
    
    # Format search results
    formatted_results = ""
    for i, result in enumerate(search_results[:5], 1):
        formatted_results += f"\n{i}. {result.get('title', 'No title')}\n"
        formatted_results += f"   URL: {result.get('url', 'No URL')}\n"
        formatted_results += f"   Content: {result.get('content', 'No content')[:500]}...\n"
    
    prompt = f"""Analyze the following claim against the search results and determine if it's accurate.

Claim: {claim}

Search Results:
{formatted_results}

Provide your analysis in the following JSON format:
{{
    "verdict": "ACCURATE" or "INACCURATE" or "PARTIALLY_ACCURATE" or "UNVERIFIABLE",
    "confidence": "HIGH" or "MEDIUM" or "LOW",
    "explanation": "Brief explanation of your verdict (2-3 sentences)",
    "evidence": "Key supporting or contradicting evidence from search results"
}}

JSON Response:"""

    try:
        response = mistral_client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
        
    except Exception as e:
        return {
            "verdict": "ERROR",
            "confidence": "LOW",
            "explanation": f"Error analyzing claim: {str(e)}",
            "evidence": ""
        }

# Main app
def main():
    # Check if API keys are provided
    if not mistral_api_key or not tavily_api_key:
        st.warning("⚠️ Please enter both Mistral and Tavily API keys in the sidebar to continue.")
        return
    
    # Initialize clients
    try:
        mistral_client = Mistral(api_key=mistral_api_key)
        tavily_client = TavilyClient(api_key=tavily_api_key)
    except Exception as e:
        st.error(f"Error initializing API clients: {str(e)}")
        return
    
    # File upload
    uploaded_file = st.file_uploader("Upload PDF Document", type=['pdf'])
    
    if uploaded_file is not None:
        # Display file info
        st.success(f"✅ Uploaded: {uploaded_file.name}")
        
        # Extract text
        with st.spinner("Extracting text from PDF..."):
            document_text = extract_text_from_pdf(uploaded_file)
        
        if not document_text:
            st.error("Could not extract text from PDF. Please try a different file.")
            return
        
        # Show extracted text in expander
        with st.expander("📝 View Extracted Text"):
            st.text_area("Document Content", document_text, height=300)
        
        # Button to start fact-checking
        if st.button("🔍 Start Fact Checking", type="primary"):
            # Extract claims
            with st.spinner("Identifying claims in the document..."):
                claims = extract_claims(mistral_client, document_text)
            
            if not claims:
                st.warning("No claims were extracted from the document.")
                return
            
            st.success(f"✅ Found {len(claims)} claims to fact-check")
            
            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Fact-check each claim
            results = []
            for i, claim_data in enumerate(claims):
                claim = claim_data.get('claim', '')
                category = claim_data.get('category', 'General')
                search_query = claim_data.get('search_query', claim)
                
                status_text.text(f"Checking claim {i+1}/{len(claims)}: {claim[:60]}...")
                
                # Search for information
                search_result = fact_check_claim(tavily_client, claim, search_query)
                
                # Analyze with Mistral
                if search_result['success']:
                    analysis = analyze_claim_with_mistral(
                        mistral_client, 
                        claim, 
                        search_result['results']
                    )
                else:
                    analysis = {
                        "verdict": "ERROR",
                        "confidence": "LOW",
                        "explanation": f"Search failed: {search_result.get('error', 'Unknown error')}",
                        "evidence": ""
                    }
                
                results.append({
                    "claim": claim,
                    "category": category,
                    "search_query": search_query,
                    "analysis": analysis,
                    "sources": search_result.get('results', [])[:3]  # Top 3 sources
                })
                
                progress_bar.progress((i + 1) / len(claims))
            
            status_text.empty()
            progress_bar.empty()
            
            # Display results
            st.markdown("---")
            st.header("📊 Fact-Check Results")
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            
            accurate = sum(1 for r in results if r['analysis'].get('verdict') == 'ACCURATE')
            inaccurate = sum(1 for r in results if r['analysis'].get('verdict') == 'INACCURATE')
            partial = sum(1 for r in results if r['analysis'].get('verdict') == 'PARTIALLY_ACCURATE')
            unverifiable = sum(1 for r in results if r['analysis'].get('verdict') in ['UNVERIFIABLE', 'ERROR'])
            
            col1.metric("✅ Accurate", accurate)
            col2.metric("❌ Inaccurate", inaccurate)
            col3.metric("⚠️ Partial", partial)
            col4.metric("❓ Unverifiable", unverifiable)
            
            st.markdown("---")
            
            # Detailed results
            for i, result in enumerate(results, 1):
                verdict = result['analysis'].get('verdict', 'UNKNOWN')
                
                # Color coding
                if verdict == 'ACCURATE':
                    icon = "✅"
                    color = "green"
                elif verdict == 'INACCURATE':
                    icon = "❌"
                    color = "red"
                elif verdict == 'PARTIALLY_ACCURATE':
                    icon = "⚠️"
                    color = "orange"
                else:
                    icon = "❓"
                    color = "gray"
                
                with st.container():
                    st.markdown(f"### {icon} Claim {i}: {result['category']}")
                    st.markdown(f"**Claim:** {result['claim']}")
                    
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        st.markdown(f"**Verdict:** :{color}[{verdict}]")
                        st.markdown(f"**Confidence:** {result['analysis'].get('confidence', 'UNKNOWN')}")
                    
                    with col2:
                        st.markdown(f"**Analysis:** {result['analysis'].get('explanation', 'No explanation provided')}")
                        if result['analysis'].get('evidence'):
                            st.markdown(f"**Evidence:** {result['analysis'].get('evidence')}")
                    
                    # Sources
                    if result['sources']:
                        with st.expander("📚 View Sources"):
                            for j, source in enumerate(result['sources'], 1):
                                st.markdown(f"**{j}. [{source.get('title', 'No title')}]({source.get('url', '#')})**")
                                st.caption(source.get('content', 'No content')[:300] + "...")
                    
                    st.markdown("---")
            
            # Download results
            st.markdown("### 💾 Download Results")
            results_json = json.dumps(results, indent=2)
            st.download_button(
                label="Download as JSON",
                data=results_json,
                file_name="fact_check_results.json",
                mime="application/json"
            )

if __name__ == "__main__":
    main()