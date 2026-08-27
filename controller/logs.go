package controller

import (
	_ "go_learn/model"
	"net/http"

	"github.com/gin-gonic/gin"
)

// GetLogsList godoc
//
//	@Summary		Get logs content
//	@Description	get log content
//	@Tags			logs
//	@Accept			json
//	@Produce		json
//	@Param			id	path		int	true	"Account ID"
//	@Success		200	{object}	model.Log
//	@Failure		400	{object}	Response{data=object} "success"
//	@Failure		404	{object}	Response "somthing is wrong"
//	@Router			/logs/content [get]
func (c *Controller) GetLogsList(ctx *gin.Context) {
	data, err := c.service.GetLogsList()

	if err != nil {
		APIResponse(ctx, http.StatusInternalServerError, "error", err.Error())
		return
	}

	ctx.JSON(http.StatusOK, APIResponse(ctx, http.StatusOK, "success", data))
}
