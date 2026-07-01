"""
ClinVar tool - get genetic variant and clinical significance information
"""

import requests
import os
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET


def get_clinvar_variants(gene_symbol: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Get ClinVar variants for a gene symbol
    
    Args:
        gene_symbol: Gene symbol (e.g., 'BRCA1', 'TP53')
        max_results: Maximum number of variants to return
        
    Returns:
        Dictionary containing variant information
    """
    try:
        # ClinVar E-utilities API
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Step 1: Search for variants by gene
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "clinvar",
            "term": f"{gene_symbol}[gene]",
            "retmax": max_results,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        if "esearchresult" not in search_data:
            return {"error": "Invalid response from ClinVar API", "variants": []}
        
        variant_ids = search_data["esearchresult"].get("idlist", [])
        total_count = int(search_data["esearchresult"].get("count", 0))
        
        if not variant_ids:
            return {
                "gene": gene_symbol,
                "total_variants": 0,
                "variants": [],
                "message": f"No ClinVar variants found for gene {gene_symbol}"
            }
        
        # Step 2: Fetch variant details
        fetch_url = f"{base_url}esummary.fcgi"
        fetch_params = {
            "db": "clinvar",
            "id": ",".join(variant_ids),
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()
        
        # Parse variant information
        variants = []
        result_data = fetch_data.get("result", {})
        
        for variant_id in variant_ids:
            if variant_id in result_data:
                variant_info = _parse_clinvar_variant(result_data[variant_id])
                if variant_info:
                    variants.append(variant_info)
        
        return {
            "gene": gene_symbol,
            "total_variants": total_count,
            "showing": len(variants),
            "variants": variants,
            "source": "ClinVar"
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "variants": []}
    except Exception as e:
        return {"error": f"Error fetching ClinVar data: {str(e)}", "variants": []}


def _parse_clinvar_variant(variant_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a single ClinVar variant from API response"""
    try:
        return {
            "variation_id": variant_data.get("variation_id"),
            "title": variant_data.get("title", "Unknown variant"),
            "clinical_significance": variant_data.get("clinical_significance", {}).get("description", "Unknown"),
            "review_status": variant_data.get("clinical_significance", {}).get("review_status", "Unknown"),
            "variation_type": variant_data.get("variation_type", "Unknown"),
            "gene_symbol": variant_data.get("genes", [{}])[0].get("symbol", "Unknown") if variant_data.get("genes") else "Unknown",
            "hgvs": variant_data.get("canonical_spdi", "Unknown"),
            "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{variant_data.get('variation_id')}/" if variant_data.get('variation_id') else None
        }
    except Exception as e:
        print(f"Error parsing variant: {str(e)}")
        return None


def get_clinvar_by_variant_id(variant_id: str) -> Dict[str, Any]:
    """
    Get detailed ClinVar information for a specific variant ID
    
    Args:
        variant_id: ClinVar variation ID (e.g., 'VCV000000001')
        
    Returns:
        Dictionary containing detailed variant information
    """
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Fetch variant summary
        fetch_url = f"{base_url}esummary.fcgi"
        fetch_params = {
            "db": "clinvar",
            "id": variant_id,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        response = requests.get(fetch_url, params=fetch_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        result_data = data.get("result", {})
        if variant_id not in result_data:
            return {
                "variant_id": variant_id,
                "error": f"Variant {variant_id} not found in ClinVar",
                "found": False
            }
        
        variant_info = _parse_clinvar_variant(result_data[variant_id])
        if variant_info:
            variant_info["found"] = True
            variant_info["source"] = "ClinVar"
            return variant_info
        else:
            return {
                "variant_id": variant_id,
                "error": "Could not parse variant data",
                "found": False
            }
            
    except requests.exceptions.RequestException as e:
        return {"variant_id": variant_id, "error": f"Network error: {str(e)}", "found": False}
    except Exception as e:
        return {"variant_id": variant_id, "error": f"Error fetching variant data: {str(e)}", "found": False}


def search_clinvar_by_condition(condition: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Search ClinVar variants associated with a specific condition/disease
    
    Args:
        condition: Disease or condition name (e.g., 'breast cancer', 'cystic fibrosis')
        max_results: Maximum number of variants to return
        
    Returns:
        Dictionary containing variants associated with the condition
    """
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Search for variants by condition
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "clinvar",
            "term": f"{condition}[disease]",
            "retmax": max_results,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        variant_ids = search_data["esearchresult"].get("idlist", [])
        total_count = int(search_data["esearchresult"].get("count", 0))
        
        if not variant_ids:
            return {
                "condition": condition,
                "total_variants": 0,
                "variants": [],
                "message": f"No ClinVar variants found for condition '{condition}'"
            }
        
        # Fetch variant details
        fetch_url = f"{base_url}esummary.fcgi"
        fetch_params = {
            "db": "clinvar",
            "id": ",".join(variant_ids),
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()
        
        # Parse variants
        variants = []
        result_data = fetch_data.get("result", {})
        
        for variant_id in variant_ids:
            if variant_id in result_data:
                variant_info = _parse_clinvar_variant(result_data[variant_id])
                if variant_info:
                    variants.append(variant_info)
        
        return {
            "condition": condition,
            "total_variants": total_count,
            "showing": len(variants),
            "variants": variants,
            "source": "ClinVar"
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "variants": []}
    except Exception as e:
        return {"error": f"Error searching ClinVar: {str(e)}", "variants": []}


def get_pathogenic_variants(gene_symbol: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Get pathogenic and likely pathogenic variants for a gene
    
    Args:
        gene_symbol: Gene symbol
        max_results: Maximum number of variants to return
        
    Returns:
        Dictionary containing pathogenic variants
    """
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Search for pathogenic variants
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "clinvar",
            "term": f"{gene_symbol}[gene] AND (pathogenic[clinical_significance] OR likely pathogenic[clinical_significance])",
            "retmax": max_results,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        variant_ids = search_data["esearchresult"].get("idlist", [])
        total_count = int(search_data["esearchresult"].get("count", 0))
        
        if not variant_ids:
            return {
                "gene": gene_symbol,
                "total_pathogenic": 0,
                "variants": [],
                "message": f"No pathogenic variants found for gene {gene_symbol}"
            }
        
        # Fetch variant details
        fetch_url = f"{base_url}esummary.fcgi"
        fetch_params = {
            "db": "clinvar",
            "id": ",".join(variant_ids),
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()
        
        # Parse variants
        variants = []
        result_data = fetch_data.get("result", {})
        
        for variant_id in variant_ids:
            if variant_id in result_data:
                variant_info = _parse_clinvar_variant(result_data[variant_id])
                if variant_info:
                    variants.append(variant_info)
        
        return {
            "gene": gene_symbol,
            "total_pathogenic": total_count,
            "showing": len(variants),
            "variants": variants,
            "source": "ClinVar"
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "variants": []}
    except Exception as e:
        return {"error": f"Error fetching pathogenic variants: {str(e)}", "variants": []}


def get_variant_summary(gene_symbol: str) -> Dict[str, Any]:
    """
    Get a summary of variant statistics for a gene
    
    Args:
        gene_symbol: Gene symbol
        
    Returns:
        Dictionary containing variant summary statistics
    """
    try:
        # Get all variants
        all_variants = get_clinvar_variants(gene_symbol, max_results=100)
        
        if all_variants.get("error"):
            return all_variants
        
        variants = all_variants.get("variants", [])
        
        # Count by clinical significance
        significance_counts = {}
        review_status_counts = {}
        variant_type_counts = {}
        
        for variant in variants:
            # Clinical significance
            sig = variant.get("clinical_significance", "Unknown")
            significance_counts[sig] = significance_counts.get(sig, 0) + 1
            
            # Review status
            review = variant.get("review_status", "Unknown")
            review_status_counts[review] = review_status_counts.get(review, 0) + 1
            
            # Variant type
            var_type = variant.get("variation_type", "Unknown")
            variant_type_counts[var_type] = variant_type_counts.get(var_type, 0) + 1
        
        return {
            "gene": gene_symbol,
            "total_variants": all_variants.get("total_variants", 0),
            "analyzed": len(variants),
            "clinical_significance_summary": significance_counts,
            "review_status_summary": review_status_counts,
            "variant_type_summary": variant_type_counts,
            "source": "ClinVar"
        }
        
    except Exception as e:
        return {"error": f"Error generating variant summary: {str(e)}"}


def search_clinvar_by_rsid(rsid: str) -> Dict[str, Any]:
    """
    Search ClinVar by dbSNP rsID
    
    Args:
        rsid: dbSNP rsID (e.g., 'rs80357906')
        
    Returns:
        Dictionary containing variant information
    """
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Clean rsID
        clean_rsid = rsid.replace("rs", "") if rsid.startswith("rs") else rsid
        
        # Search for variant by rsID
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "clinvar",
            "term": f"{clean_rsid}[rsid]",
            "retmax": 10,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        variant_ids = search_data["esearchresult"].get("idlist", [])
        
        if not variant_ids:
            return {
                "rsid": rsid,
                "error": f"No ClinVar entries found for rsID {rsid}",
                "found": False
            }
        
        # Fetch variant details
        fetch_url = f"{base_url}esummary.fcgi"
        fetch_params = {
            "db": "clinvar",
            "id": ",".join(variant_ids),
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()
        
        # Parse variants
        variants = []
        result_data = fetch_data.get("result", {})
        
        for variant_id in variant_ids:
            if variant_id in result_data:
                variant_info = _parse_clinvar_variant(result_data[variant_id])
                if variant_info:
                    variants.append(variant_info)
        
        return {
            "rsid": rsid,
            "total_found": len(variants),
            "variants": variants,
            "found": True,
            "source": "ClinVar"
        }
        
    except requests.exceptions.RequestException as e:
        return {"rsid": rsid, "error": f"Network error: {str(e)}", "found": False}
    except Exception as e:
        return {"rsid": rsid, "error": f"Error fetching variant: {str(e)}", "found": False}


def get_clinical_significance_summary(gene_symbol: str) -> Dict[str, Any]:
    """
    Get a summary of clinical significance categories for a gene's variants
    
    Args:
        gene_symbol: Gene symbol
        
    Returns:
        Dictionary containing clinical significance summary
    """
    try:
        summary = get_variant_summary(gene_symbol)
        
        if summary.get("error"):
            return summary
        
        sig_counts = summary.get("clinical_significance_summary", {})
        
        # Categorize variants
        pathogenic_count = sig_counts.get("Pathogenic", 0) + sig_counts.get("Likely pathogenic", 0)
        benign_count = sig_counts.get("Benign", 0) + sig_counts.get("Likely benign", 0)
        vus_count = sig_counts.get("Uncertain significance", 0)
        other_count = sum(sig_counts.values()) - pathogenic_count - benign_count - vus_count
        
        return {
            "gene": gene_symbol,
            "total_variants": summary.get("total_variants", 0),
            "categories": {
                "pathogenic_or_likely_pathogenic": pathogenic_count,
                "benign_or_likely_benign": benign_count,
                "uncertain_significance": vus_count,
                "other": other_count
            },
            "detailed_counts": sig_counts,
            "interpretation": _interpret_clinical_significance(pathogenic_count, benign_count, vus_count),
            "source": "ClinVar"
        }
        
    except Exception as e:
        return {"error": f"Error generating clinical significance summary: {str(e)}"}


def _interpret_clinical_significance(pathogenic: int, benign: int, vus: int) -> str:
    """Generate interpretation of clinical significance data"""
    total = pathogenic + benign + vus
    
    if total == 0:
        return "No variants with clinical significance data available"
    
    path_percent = (pathogenic / total * 100) if total > 0 else 0
    
    if pathogenic > 50:
        return f"Gene has a large number of pathogenic variants ({pathogenic}), suggesting clinical relevance in disease"
    elif pathogenic > 10:
        return f"Gene has moderate number of pathogenic variants ({pathogenic})"
    elif pathogenic > 0:
        return f"Gene has {pathogenic} pathogenic variant(s) reported"
    else:
        return "No pathogenic variants currently reported in ClinVar"


def get_variants_by_significance(gene_symbol: str, significance: str = "pathogenic") -> Dict[str, Any]:
    """
    Get variants filtered by clinical significance
    
    Args:
        gene_symbol: Gene symbol
        significance: Clinical significance to filter by 
                     ('pathogenic', 'benign', 'uncertain', 'likely_pathogenic', 'likely_benign')
        
    Returns:
        Dictionary containing filtered variants
    """
    # Map common terms to ClinVar search terms
    significance_map = {
        "pathogenic": "pathogenic[clinical_significance]",
        "likely_pathogenic": "likely pathogenic[clinical_significance]",
        "benign": "benign[clinical_significance]",
        "likely_benign": "likely benign[clinical_significance]",
        "uncertain": "uncertain significance[clinical_significance]",
        "vus": "uncertain significance[clinical_significance]"
    }
    
    search_term = significance_map.get(significance.lower(), significance)
    
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "clinvar",
            "term": f"{gene_symbol}[gene] AND {search_term}",
            "retmax": 20,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        variant_ids = search_data["esearchresult"].get("idlist", [])
        total_count = int(search_data["esearchresult"].get("count", 0))
        
        if not variant_ids:
            return {
                "gene": gene_symbol,
                "significance_filter": significance,
                "total_found": 0,
                "variants": [],
                "message": f"No {significance} variants found for {gene_symbol}"
            }
        
        # Fetch details
        fetch_url = f"{base_url}esummary.fcgi"
        fetch_params = {
            "db": "clinvar",
            "id": ",".join(variant_ids[:10]),  # Limit to first 10 for details
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent_studio"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()
        
        variants = []
        result_data = fetch_data.get("result", {})
        
        for variant_id in variant_ids[:10]:
            if variant_id in result_data:
                variant_info = _parse_clinvar_variant(result_data[variant_id])
                if variant_info:
                    variants.append(variant_info)
        
        return {
            "gene": gene_symbol,
            "significance_filter": significance,
            "total_found": total_count,
            "showing": len(variants),
            "variants": variants,
            "source": "ClinVar"
        }
        
    except Exception as e:
        return {"error": f"Error fetching {significance} variants: {str(e)}"}

