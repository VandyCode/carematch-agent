variable "project_id" {
  description = "Google Cloud Project ID for CareMatch deployment"
  type        = string
}

variable "region" {
  description = "Primary GCP region for Cloud Run and Artifact Registry"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "carematch-agent"
}

variable "container_image" {
  description = "Container image URI for CareMatch (e.g., us-central1-docker.pkg.dev/YOUR_PROJECT/carematch-agent-repo/carematch-agent:latest)"
  type        = string
}

variable "model_name" {
  description = "Default public Gemini model identifier"
  type        = string
  default     = "gemini-2.5-flash"
}

variable "enable_live_cms_api" {
  description = "Whether to query live public CMS.gov / NPPES endpoints at runtime"
  type        = string
  default     = "true"
}
