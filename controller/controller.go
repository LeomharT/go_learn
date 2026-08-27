package controller

import (
	"go_learn/service"
)

type Controller struct {
	service *service.Service
}

func NewController(s *service.Service) *Controller {
	return &Controller{service: s}
}
