variable "rule_name" {
  type = string
}

variable "event_source" {
  type        = string
  description = "EventBridge event source filter (e.g. 'racetrack')"
}

variable "detail_type" {
  type        = string
  description = "EventBridge detail-type filter (e.g. 'SessionIngested')"
}

variable "target_function_arn" {
  type = string
}

variable "target_function_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
