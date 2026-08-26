package controller

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func (c *Controller) GetLogsList(ctx *gin.Context) {
	ctx.JSON(http.StatusOK, c.service.GetLogsList())
}
