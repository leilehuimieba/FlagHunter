# GHOSTCREW Automated Penetration Testing Workflows

def get_available_workflows():
    """
    Get all available automated workflows.
    All workflows can use any configured tools - no restrictions.
    """
    
    workflows = {
        "reconnaissance": {
            "name": "Reconnaissance and Discovery",
            "description": "Comprehensive information gathering and target profiling",
            "steps": [
                "Perform comprehensive reconnaissance on {target}",
                "Discover subdomains and DNS information",  
                "Scan for open ports and services",
                "Identify technology stack and fingerprints",
                "Gather historical data and archived content"
            ]
        },
        
        "web_application": {
            "name": "Web Application Security Assessment", 
            "description": "Comprehensive web application penetration testing",
            "steps": [
                "Discover web directories and hidden content on {target}",
                "Test for SQL injection vulnerabilities",
                "Scan for web application vulnerabilities and misconfigurations", 
                "Analyze SSL/TLS configuration and security",
                "Test for authentication and session management flaws",
                "Check for file inclusion and upload vulnerabilities"
            ]
        },
        
        "network_infrastructure": {
            "name": "Network Infrastructure Penetration Test",
            "description": "Network-focused penetration testing and exploitation",
            "steps": [
                "Scan network range {target} for live hosts and services",
                "Perform detailed service enumeration and version detection",
                "Scan for known vulnerabilities in discovered services",
                "Test for network service misconfigurations",
                "Attempt exploitation of discovered vulnerabilities",
                "Assess network segmentation and access controls"
            ]
        },
        
        "full_penetration_test": {
            "name": "Complete Penetration Test",
            "description": "Full-scope penetration testing methodology",
            "steps": [
                "Phase 1: Comprehensive reconnaissance and asset discovery on {target}",
                "Phase 2: Service enumeration and technology fingerprinting",
                "Phase 3: Vulnerability scanning and identification", 
                "Phase 4: Web application security testing (if applicable)",
                "Phase 5: Network service exploitation attempts",
                "Phase 6: Post-exploitation and privilege escalation testing",
                "Phase 7: Document findings and provide comprehensive remediation guidance"
            ]
        }
    }
    
    return workflows

def get_workflow_by_key(workflow_key):
    """Get a specific workflow by its key"""
    workflows = get_available_workflows()
    return workflows.get(workflow_key, None)

def list_workflow_names():
    """Get a list of all workflow names for display"""
    workflows = get_available_workflows()
    return [(key, workflow["name"]) for key, workflow in workflows.items()] 