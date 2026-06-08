variable "api_name" {
  type = string
}

variable "routes" {
  type = map(object({
    invoke_arn    = string
    function_name = string
  }))
  description = "Map of route key (e.g. 'GET /sessions') to Lambda invoke_arn and function_name"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "tags" {
  type    = map(string)
  default = {}
}
