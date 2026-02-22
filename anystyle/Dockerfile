FROM ruby:3.3

# Install dependencies
RUN apt-get update && apt-get install -y \
    libxml2 \
    libxml2-dev \
    libxslt1-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Ensure gem binaries are in PATH
ENV GEM_HOME="/usr/local/bundle"
ENV PATH="$GEM_HOME/bin:$PATH"

# Install Anystyle CLI
RUN gem install anystyle-cli

# Verify installation of Anystyle
RUN anystyle -h || (echo "Installation failed" && exit 1)

# Verify installation of pdftotext
RUN pdftotext -v || (echo "pdftotext installation failed" && exit 1)
