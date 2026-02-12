from setuptools import setup, find_packages

setup(
    name="niv_tools",
    version="0.2.0",
    description="AI Developer Tools for Niv AI — extends Frappe Assistant Core (FAC) with 7 custom MCP tools",
    author="Ravindra Kulhari",
    author_email="kulharir7@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
)
