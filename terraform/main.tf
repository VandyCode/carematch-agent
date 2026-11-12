terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_artifact_registry_repository" "carematch_repo" {
  location      = var.region
  repository_id = "${var.service_name}-repo"
  description   = "Container repository for CareMatch Multi-Agent Healthcare Quality & Coverage Navigator"
  format        = "DOCKER"
}

resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "CAREMATCH_GEMINI_API_KEY"
  replication {
    auto {}
  }
}

resource "google_cloud_run_v2_service" "carematch_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.container_image
      ports {
        container_port = 8000
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "CAREMATCH_MODEL"
        value = var.model_name
      }
      env {
        name  = "CAREMATCH_CMS_LIVE_API"
        value = var.enable_live_cms_api
      }
      env {
        name  = "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
        value = "true"
      }
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }
  }
}
