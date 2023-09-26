from keras import ops
from keras.api_export import keras_export
from keras.layers.core.dense import Dense
from keras.layers.layer import Layer


@keras_export("keras.layers.GroupQueryAttention")
class GroupedQueryAttention(Layer):
    """Grouped Query Attention layer.

    This is an implementation of grouped-query attention introduced by
    [Ainslie et al., 2023](https://arxiv.org/abs/2305.13245). Here
    `num_key_value_heads` denotes number of groups, setting
    `num_key_value_heads` to 1 is equivalent to multi-query attention, and
    when `num_key_value_heads` is equal to `num_query_heads` it is equivalent
    to multi-head attention.

    This layer first projects `query`, `key`, and `value` tensors. Then, `key`
    and `value` are repeated to match the number of heads of `query`.

    Then, the `query` is scaled and dot-producted with `key` tensors. These are
    softmaxed to obtain attention probabilities. The value tensors are then
    interpolated by these probabilities and concatenated back to a single
    tensor.

    Args:
        head_dim: Size of each attention head.
        num_query_heads: Number of query attention heads.
        num_key_value_heads: Number of key and value attention heads.
        use_bias: Boolean, whether the dense layers use bias vectors/matrices.

    Call arguments:
        query: Query tensor of shape `(batch_dim, target_seq_len, feature_dim)`,
            where `batch_dim` is batch size, `target_seq_len` is the length of
            target sequence, and `feature_dim` is dimension of feature.
        value: Value tensor of shape `(batch_dim, source_seq_len, feature_dim)`,
            where `batch_dim` is batch size, `source_seq_len` is the length of
            source sequence, and `feature_dim` is dimension of feature.
        key: Optional key tensor of shape
            `(batch_dim, source_seq_len, feature_dim)`. If not given, will use
            `value` for both `key` and `value`, which is most common case.
        mask: A boolean mask of shape
            `(batch_dim, target_seq_len, source_seq_len)`, that prevents
            attention to certain positions. The boolean mask specifies which
            query elements can attend to which key elements, where 1 indicates
            attention and 0 indicates no attention. Broadcasting can happen for
            the missing batch dimensions and the head dimension.
        return_attention_scores: A boolean to indicate whether the output
            should be `(attention_output, attention_scores)` if `True`, or
            `attention_output` if `False`. Defaults to `False`.
        training: Python boolean indicating whether the layer should behave in
            training mode (adding dropout) or in inference mode (no dropout).
            Will go with either using the training mode of the parent
            layer/model or `False` (inference) if there is no parent layer.

    Returns:
        attention_output: Result of the computation, of shape
            `(batch_dim, target_seq_len, feature_dim)`, where `target_seq_len`
            is for target sequence length and `feature_dim` is the query input
            last dim.
        attention_scores: (Optional) attention coefficients.
    """

    def __init__(
        self,
        head_dim,
        num_query_heads,
        num_key_value_heads,
        use_bias=False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.head_dim = head_dim
        self.num_query_heads = num_query_heads
        self.num_key_value_heads = num_key_value_heads
        self.num_repeats = num_query_heads // num_key_value_heads
        self.use_bias = use_bias

    def build(
        self,
        query_shape,
        value_shape,
        key_shape=None,
    ):
        key_shape = value_shape if key_shape is None else key_shape
        self.feature_dim = query_shape[-1]
        self._query_dense = Dense(
            self.num_query_heads * self.head_dim,
            use_bias=self.use_bias,
            name="query",
        )
        self._query_dense.build(query_shape)

        self._key_dense = Dense(
            self.num_key_value_heads * self.head_dim,
            use_bias=self.use_bias,
            name="key",
        )
        self._key_dense.build(key_shape)

        self._value_dense = Dense(
            self.num_key_value_heads * self.head_dim,
            use_bias=self.use_bias,
            name="value",
        )
        self._value_dense.build(value_shape)

        self._output_dense = Dense(
            self.feature_dim, use_bias=self.use_bias, name="attention_output"
        )
        output_dense_input_shape = list(
            self._query_dense.compute_output_shape(query_shape)
        )
        self._output_dense.build(output_dense_input_shape)
        self.built = True

    def call(
        self,
        query,
        value,
        key=None,
        mask=None,
        return_attention_scores=False,
        training=None,
    ):
        if key is None:
            key = value
        batch_dim, target_seq_len, _ = ops.shape(
            query
        )  # (batch_dim, target_seq_len, feature_dim)
        _, source_seq_len, _ = ops.shape(
            value
        )  # (batch_dim, source_seq_len, feature_dim)

        query = self._query_dense(query)
        key = self._key_dense(key)
        value = self._value_dense(value)

        query = ops.reshape(
            query,
            (batch_dim, target_seq_len, self.num_query_heads, self.head_dim),
        )  # (batch_dim, target_seq_len, query_heads, head_dim)
        key = ops.reshape(
            key,
            (
                batch_dim,
                source_seq_len,
                self.num_key_value_heads,
                self.head_dim,
            ),
        )  # (batch_dim, source_seq_len, key_value_heads, head_dim)
        value = ops.reshape(
            value,
            (
                batch_dim,
                source_seq_len,
                self.num_key_value_heads,
                self.head_dim,
            ),
        )  # (batch_dim, source_seq_len, key_value_heads, head_dim)

        key = ops.repeat(
            key, self.num_repeats, axis=2
        )  # (batch_dim, source_seq_len, query_heads, head_dim)
        value = ops.repeat(
            value, self.num_repeats, axis=2
        )  # (batch_dim, source_seq_len, query_heads, head_dim)

        query = ops.transpose(
            query, axes=(0, 2, 1, 3)
        )  # (batch_dim, query_heads, target_seq_len, head_dim)
        key = ops.transpose(
            key, axes=(0, 2, 3, 1)
        )  # (batch_dim, query_heads, head_dim, source_seq_len)
        value = ops.transpose(
            value, axes=(0, 2, 1, 3)
        )  # (batch_dim, query_heads, source_seq_len, head_dim)

        output, scores = self._compute_attention(query, key, value, mask=mask)

        output = ops.transpose(
            output, axes=(0, 2, 1, 3)
        )  # (batch_dim, target_seq_len, query_heads, head_dim)
        output = ops.reshape(
            output,
            (batch_dim, target_seq_len, self.num_query_heads * self.head_dim),
        )  # (batch_dim, target_seq_len, query_heads * head_dim)
        output = self._output_dense(
            output
        )  # (batch_dim, target_seq_len, feature_dim)

        if return_attention_scores:
            return output, scores
        return output

    def _compute_attention(self, query, key, value, mask=None):
        query = ops.multiply(
            query,
            1.0 / ops.sqrt(ops.cast(self.head_dim, query.dtype)),
        )
        scores = ops.matmul(
            query, key
        )  # (batch_dim, query_heads, target_seq_len, source_seq_len)
        if mask is not None:
            scores = scores + mask
        output = ops.matmul(
            scores, value
        )  # (batch_dim, query_heads, target_seq_len, head_dim)
        return output, scores

    def get_config(self):
        config = {
            "head_dim": self.head_dim,
            "num_query_heads": self.num_query_heads,
            "num_key_value_heads": self.num_key_value_heads,
            "use_bias": self.use_bias,
        }
        base_config = super().get_config()
        return {**base_config, **config}
