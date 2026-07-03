# Copyright 2026 EPAM Systems, Inc. (“EPAM”)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ipaddress
import yaml
import requests
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Self
from urllib.parse import urlsplit

from codemie.configs.config import config
from codemie.rest_api.models.permission import ResourceType


def validate_public_key_url(url: str, allowed_domains: list[str]) -> None:
    """Raise ValueError unless url is an https URL whose host is within allowed_domains.

    A host matches an allowed domain if it equals the domain or is a subdomain of it.
    An empty allowed_domains list rejects every URL (fail-closed).
    """
    parsed_url = urlsplit(url)
    if parsed_url.scheme.lower() != "https":
        raise ValueError(f"public_key_url must use https: {url}")

    hostname = parsed_url.hostname
    if not hostname:
        raise ValueError(f"public_key_url must have a valid host: {url}")

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"public_key_url has an invalid host: {url}") from exc

    try:
        ipaddress.ip_address(ascii_hostname)
    except ValueError:
        pass
    else:
        raise ValueError(f"public_key_url host must not be an IP literal: {url}")

    for domain in allowed_domains:
        normalized_domain = domain.lower()
        if ascii_hostname == normalized_domain or ascii_hostname.endswith(f".{normalized_domain}"):
            return

    raise ValueError(f"public_key_url host '{ascii_hostname}' is not in the allowed domains list")


class AuthorizedApplication(BaseModel):
    name: str
    public_key_url: Optional[str] = None
    public_key_path: Optional[str] = None
    allowed_resources: list[ResourceType] = Field(default_factory=list)

    _REQUEST_ID_HEADER = "X-Request-ID"

    @model_validator(mode="after")
    def check_public_key(self) -> Self:
        if not bool(self.public_key_url) ^ bool(self.public_key_path):
            raise ValueError("Either public_key_url or public_key_path must be present")

        if self.public_key_url:
            validate_public_key_url(self.public_key_url, config.AUTHORIZED_APPS_ALLOWED_KEY_DOMAINS)

        return self

    def get_public_key(self, x_request_id: str) -> bytes:
        """Returns the public key as bytes from either URL or local path."""
        try:
            if self.public_key_url:
                validate_public_key_url(self.public_key_url, config.AUTHORIZED_APPS_ALLOWED_KEY_DOMAINS)
                response = requests.get(self.public_key_url, params={"request_id": x_request_id}, timeout=10)
                response.raise_for_status()
                return response.content
            elif self.public_key_path:
                return Path(self.public_key_path).read_bytes()
            else:
                raise ValueError("No public key URL or path provided")
        except Exception as exc:
            raise ValueError(f"Error retrieving public key: {exc}") from exc


class AuthorizedApplicationsConfig(BaseModel):
    """Load authorized-applications-config.yaml into Pydantic model"""

    applications: list[AuthorizedApplication] = Field(default_factory=list)
    config_path: Path = Field(default=Path(f"{config.AUTHORIZED_APPS_CONFIG_DIR}/authorized-applications-config.yaml"))

    _TAG = "AuthorizedApplicationsConfig"
    _CONFIGS_KEY = "authorized_applications"

    @property
    def applications_names(self) -> list[str]:
        """Returns list of app names"""
        return [app.name for app in self.applications]

    def find_by_name(self, name: str) -> Optional[AuthorizedApplication]:
        """Find application by name"""
        return next((app for app in self.applications if app.name == name), None)

    def model_post_init(self, _) -> None:
        self._load_config()

    def _load_config(self) -> None:
        try:
            config_data = yaml.safe_load(self.config_path.read_text())

            if not isinstance(config_data, dict):
                raise ValueError(f"[{self._TAG}] Invalid YAML structure: root must be a dictionary")

            self.applications = [AuthorizedApplication(**item) for item in config_data.get(self._CONFIGS_KEY, [])]
        except yaml.YAMLError as exc:
            raise ValueError(f"[{self._TAG}]Error parsing YAML configuration: {exc}")


authorized_applications_config = AuthorizedApplicationsConfig()
