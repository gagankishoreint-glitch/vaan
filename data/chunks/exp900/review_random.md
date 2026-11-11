# Random chunks per paper (eyeball these)

## attention (59 chunks)

### `attn-v7:s3.4:c0000` p.5 §3.4 Embeddings and Softmax [caption]
```
Similarly to other sequence transduction models, we use learned embeddings to convert the input
tokens and output tokens to vectors of dimension dmodel. We also use the usual learned linear transfor-
mation and softmax function to convert the decoder output to predicted next-token probabilities. In
our model, we share the same weight matrix between the two embedding layers and the pre-softmax
linear transformation, similar to [30]. In the embedding layers, we multiply those weights by √dmodel.
Table 1: Maximum path lengths, per-layer complexity and minimum number of sequential operations
for different layer types. n is the sequence length, d is the representation dimension, k is the kernel
size of convolutions and r the size of the neighborhood in restricted self-attention.
Layer Type
Complexity per Layer
Sequential
Maximum Path Length
Operations
Self-Attention
O(n2 ·
```

### `attn-v7:s3:c0000` p.2 §3 Model Architecture [caption]
```
Most competitive neural sequence transduction models have an encoder-decoder structure [5, 2, 35].
Here, the encoder maps an input sequence of symbol representations (x1, ..., xn) to a sequence
of continuous representations z = (z1, ..., zn). Given z, the decoder then generates an output
sequence (y1, ..., ym) of symbols one element at a time. At each step the model is auto-regressive
[10], consuming the previously generated symbols as additional input when generating the next.
Figure 1: The Transformer - model architecture.
The Transformer follows this overall architecture using stacked self-attention and point-wise, fully
connected layers for both the encoder and decoder, shown in the left and right halves of Figure 1,
respectively.
```

### `attn-v7:s4:c0001` p.6 §4 Why Self-Attention [ok]
```
transduction tasks. One key factor affecting the
ability to learn such dependencies is the length of the paths forward and backward signals have to
traverse in the network. The shorter these paths between any combination of positions in the input
and output sequences, the easier it is to learn long-range dependencies [12]. Hence we also compare
the maximum path length between any two input and output positions in networks composed of the
different layer types.
As noted in Table 1, a self-attention layer connects all positions with a constant number of sequentially
executed operations, whereas a recurrent layer requires O(n) sequential operations. In terms of
computational complexity, self-attention layers are faster than recurrent layers when the sequence
length n is smaller than the representation dimensionality d, which is most often the case with
sentence representations used by
```

### `attn-v7:s6.3:c0000` p.9 §6.3 English Constituency Parsing [ok]
```
To evaluate if the Transformer can generalize to other tasks we performed experiments on English
constituency parsing. This task presents specific challenges: the output is subject to strong structural
constraints and is significantly longer than the input. Furthermore, RNN sequence-to-sequence
models have not been able to attain state-of-the-art results in small-data regimes [37].
We trained a 4-layer transformer with dmodel = 1024 on the Wall Street Journal (WSJ) portion of the
Penn Treebank [25], about 40K training sentences. We also trained it in a semi-supervised setting,
using the larger high-confidence and BerkleyParser corpora from with approximately 17M sentences
[37]. We used a vocabulary of 16K tokens for the WSJ only setting and a vocabulary of 32K tokens
for the semi-supervised setting.
We performed only a small number of experiments to select the dropout, both attention
```

### `attn-v7:s1:c0000` p.2 §1 Introduction [ok]
```
Recurrent neural networks, long short-term memory [13] and gated recurrent [7] neural networks
in particular, have been firmly established as state of the art approaches in sequence modeling and
transduction problems such as language modeling and machine translation [35, 2, 5]. Numerous
efforts have since continued to push the boundaries of recurrent language models and encoder-decoder
architectures [38, 24, 15].
Recurrent models typically factor computation along the symbol positions of the input and output
sequences. Aligning the positions to steps in computation time, they generate a sequence of hidden
states ht, as a function of the previous hidden state ht−1 and the input for position t. This inherently
sequential nature precludes parallelization within training examples, which becomes critical at longer
sequence lengths, as memory constraints limit batching across examples. Recent
```

### `attn-v7:s1:c0001` p.2 §1 Introduction [ok]
```
within training examples, which becomes critical at longer
sequence lengths, as memory constraints limit batching across examples. Recent work has achieved
significant improvements in computational efficiency through factorization tricks [21] and conditional
computation [32], while also improving model performance in case of the latter. The fundamental
constraint of sequential computation, however, remains.
Attention mechanisms have become an integral part of compelling sequence modeling and transduc-
tion models in various tasks, allowing modeling of dependencies without regard to their distance in
the input or output sequences [2, 19]. In all but a few cases [27], however, such attention mechanisms
are used in conjunction with a recurrent network.
In this work we propose the Transformer, a model architecture eschewing recurrence and instead
relying entirely on an attention mechanism
```

### `attn-v7:s7:c0007` p.10 §7 Conclusion [ok]
```
and Mark Johnson. Effective self-training for parsing. In
Proceedings of the Human Language Technology Conference of the NAACL, Main Conference,
pages 152–159. ACL, June 2006.
[27] Ankur Parikh, Oscar Täckström, Dipanjan Das, and Jakob Uszkoreit. A decomposable attention
model. In Empirical Methods in Natural Language Processing, 2016.
[28] Romain Paulus, Caiming Xiong, and Richard Socher. A deep reinforced model for abstractive
summarization. arXiv preprint arXiv:1705.04304, 2017.
[29] Slav Petrov, Leon Barrett, Romain Thibaux, and Dan Klein. Learning accurate, compact,
and interpretable tree annotation. In Proceedings of the 21st International Conference on
Computational Linguistics and 44th Annual Meeting of the ACL, pages 433–440. ACL, July
2006.
[30] Ofir Press and Lior Wolf. Using the output embedding to improve language models. arXiv
preprint arXiv:1608.05859, 2016.
[31] Rico
```

### `attn-v7:s5.4:c0001` p.7 §5.4 Regularization [ok]
```
Dropout
We apply dropout [33] to the output of each sub-layer, before it is added to the
sub-layer input and normalized. In addition, we apply dropout to the sums of the embeddings and the
positional encodings in both the encoder and decoder stacks. For the base model, we use a rate of
Pdrop = 0.1.
Label Smoothing
During training, we employed label smoothing of value ϵls = 0.1 [36]. This
hurts perplexity, as the model learns to be more unsure, but improves accuracy and BLEU score.
```

### `attn-v7:s2:c0000` p.2 §2 Background [ok]
```
The goal of reducing sequential computation also forms the foundation of the Extended Neural GPU
[16], ByteNet [18] and ConvS2S [9], all of which use convolutional neural networks as basic building
block, computing hidden representations in parallel for all input and output positions. In these models,
the number of operations required to relate signals from two arbitrary input or output positions grows
in the distance between positions, linearly for ConvS2S and logarithmically for ByteNet. This makes
it more difficult to learn dependencies between distant positions [12]. In the Transformer this is
reduced to a constant number of operations, albeit at the cost of reduced effective resolution due
to averaging attention-weighted positions, an effect we counteract with Multi-Head Attention as
described in section 3.2.
Self-attention, sometimes called intra-attention is an attention
```

### `attn-v7:s3.5:c0001` p.6 §3.5 Positional Encoding [ok]
```
positional encoding
corresponds to a sinusoid. The wavelengths form a geometric progression from 2π to 10000 · 2π. We
chose this function because we hypothesized it would allow the model to easily learn to attend by
relative positions, since for any fixed offset k, PEpos+k can be represented as a linear function of
PEpos.
We also experimented with using learned positional embeddings [9] instead, and found that the two
versions produced nearly identical results (see Table 3 row (E)). We chose the sinusoidal version
because it may allow the model to extrapolate to sequence lengths longer than the ones encountered
during training.
```

## hnet (183 chunks)

### `hnet-v2:s5:c0041` p.23 §5 Conclusion [ok]
```
partitioning sequences using fixed-size intervals. Many strategies could
be used to aggregate a width-𝑘window, including direct downsampling, average pooling, linear transformations that mix
across the chunk, convolutions, and more; we lump these together as pooling operations.
Hourglass Transformer (Nawrot, Tworkowski, et al. 2022) and MegaByte (Yu, Simig, et al. 2023) exemplify this strategy.
Other recent variants include the Block Transformer (Ho et al. 2024) and Multiscale Byte Language Model (MBLM) (Egli,
Manica, and Born 2025), which use similar multi-stage static chunking architectures. Concurrently to H-Net, the MBLM
also proposes using Mamba layers in the outer stages.
These approaches share conceptual similarity with spatial pooling operations in vision models that reduce resolution
through fixed-window aggregation (Krizhevsky, Sutskever, and Hinton 2012; He et al. 2016).
```

### `hnet-v2:s1:c0011` p.1 §1 Introduction [ok]
```
the pretrained H-Net is dramatically more robust to textual perturbations
than the token-based Transformer, as evaluated on the noisy HellaSwag suite of benchmarks.
• Interpretability. Qualitative visualizations of learned boundaries reveal that H-Net automatically discovers seman-
tically coherent units without explicit supervision, validating that end-to-end learning successfully detects the
structural patterns traditionally imposed through handcrafted tokenization.
• Other languages. H-Net’s improvements are even more pronounced on languages without obvious segmentation
cues, including Chinese and code (59.9 →66.3 on XWinograd-zh compared to tokenized Transformer) and DNA
language modeling (3.6× improved data efficiency compared to isotropic models).
We publicly release model code5 and pretrained checkpoints6.
```

### `hnet-v2:s5:c0021` p.23 §5 Conclusion [ok]
```
(Volume 1: Long Papers). Ed. by Anna Rogers, Jordan Boyd-Graber, and Naoaki Okazaki. Toronto, Canada: Association
for Computational Linguistics, July 2023, pp. 15991–16111. doi: 10.18653/v1/2023.acl-long.891. url: https:
//aclanthology.org/2023.acl-long.891/.
[68]
Niklas Muennighoff, Zitong Yang, Weijia Shi, Xiang Lisa Li, Li Fei-Fei, Hannaneh Hajishirzi, Luke Zettlemoyer,
Percy Liang, Emmanuel Candès, and Tatsunori Hashimoto. “S1: Simple Test-Time Scaling”. In: arXiv preprint
arXiv:2501.19393 (2025).
[69]
Piotr Nawrot, Jan Chorowski, Adrian Lancucki, and Edoardo Maria Ponti. “Efficient Transformers with Dynamic
Token Pooling”. In: Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (Volume
1: Long Papers). 2023, pp. 6403–6417.
[70]
Piotr Nawrot, Szymon Tworkowski, Michał Tyrolski, Łukasz Kaiser, Yuhuai Wu, Christian Szegedy, and Henryk
Michalewski.
```

### `hnet-v2:s3:c0006` p.10 §3 Experiments [ok]
```
et
al. 2020) (i.e., GPT-3 L and GPT-3 XL) variant of the tokenized Transformer (760M and 1.3B parameters respectively).
Experimental Setup.
Following established practice (Xue et al. 2022; Wang et al. 2024; Slagle 2024), we measure
performance using bits-per-byte (BPB) to ensure comparability across different input representations. For tokenized models,
this amounts to simply rescaling the total negative log likelihood of a sequence (in tokens) by the total number of bytes. In
addition, we systematically control the data and compute budget for all models (see Table 1), matching all models carefully
in both bytes-per-batch and FLOPs-per-byte:13
• Data Budget: We train all models on the 100B token subset sampled from the FineWeb-Edu dataset (Penedo et al.
2024). All tokenizer-free models process 8192 utf-8 encoded bytes per sequence, while the Transformer uses 1792
tokens from the GPT2
```

### `hnet-v2:s1:c0006` p.1 §1 Introduction [ok]
```
where outer stages capture fine-grained patterns while
inner stages operate on coarse representations akin to traditional tokens. Crucially, while the main network contains
the bulk of parameters and can be any standard architecture designed for operating on tokenized language—such as a
Transformer (Vaswani et al. 2017) or state space model (SSM) (Gu and Dao 2024)—we show that the encoder and decoder
networks are strongly improved by using SSMs, which have an inductive bias for compression (Gu 2025).
Dynamic Chunking.
H-Net’s core is a novel dynamic chunking (DC) mechanism which interfaces between the main
network and the encoder/decoder networks, learning how to segment data while using standard differentiable optimization.
DC is composed of two complementary new techniques: (i) a routing module which predicts boundaries between adjacent
elements through a similarity score (ii) and a
```

### `hnet-v2:s2.1:c0006` p.4 §2.1 Architectural Overview [ok]
```
and (ii) higher-level abstractions benefit from increased processing power.
The main network functions as a standard language model and can employ any sequence mixing architecture. We
default to Transformer layers for two reasons: compressed representations align well with Transformers’ strengths in
processing discrete, semantically-rich tokens, and this choice enables more controlled comparison with traditional BPE-
based Transformer baselines in our experiments. However, the modular design also allows straightforward substitution
with alternative architectures (e.g., a state space model, hybrid, or H-Net itself) as explored in our ablations.
Architectural Guidelines.
Compared to standard isotropic models, the H-Net’s structure introduces several new
dimensions of architectural parameters to balance the parameter/compute allocation to each network. To simplify the
search space, we
```

### `hnet-v2:s5:c0003` p.23 §5 Conclusion [ok]
```
In: arXiv preprint
arXiv:2004.05150 (2020).
[5]
Yoshua Bengio, Nicholas Léonard, and Aaron Courville. “Estimating or Propagating Gradients Through Stochastic
Neurons for Conditional Computation”. In: arXiv preprint arXiv:1308.3432 (2013).
[6]
Aviv Bick, Kevin Li, Eric Xing, J Zico Kolter, and Albert Gu. “Transformers to SSMs: Distilling Quadratic Knowledge
to Subquadratic Models”. In: Advances in Neural Information Processing Systems 37 (2024), pp. 31788–31812.
[7]
Yonatan Bisk, Rowan Zellers, Jianfeng Gao, Yejin Choi, et al. “PIQA: Reasoning About Physical Commonsense in
Natural Language”. In: Proceedings of the AAAI conference on artificial intelligence. Vol. 34. 05. 2020, pp. 7432–7439.
[8]
Daniel Bolya, Cheng-Yang Fu, Xiaoliang Dai, Peizhao Zhang, Christoph Feichtenhofer, and Judy Hoffman. “Token
Merging: Your VIT but Faster”. In: arXiv preprint arXiv:2210.09461 (2022).
[9]
Garyk
```

### `hnet-v2:s4:c0011` p.22 §4 Discussion [ok]
```
an exponential number of these, so computing the exact BPB is intractable; however, concurrent
work (Vieira et al. 2024) shows that the standard BPB calculation indeed overestimates BPB. Due to the high computational
overhead of estimating the true BPB, we only provide the standard (inexact) value; nevertheless, H-Net’s superior
performance on downstreams provides supporting evidence that it scales better than BPE models.
```

### `hnet-v2:s2.1:c0001` p.4 §2.1 Architectural Overview [ok]
```
encoder networks as E𝑠and decoder networks as D𝑠for stages 0 ≤𝑠< 𝑆, with the main network
M residing only at the final stage 𝑠= 𝑆. For example, a two-stage model contains E0, E1, M, D1, and D0, as illustrated
4Chunking is a formal concept from cognitive psychology central to human memory and cognition, and is the inspiration for this work’s terminology.
5https://github.com/goombalab/hnet
6https://huggingface.co/cartesia-ai
in Figure 1-(Left). Throughout this paper, we use superscripts to denote stage indices, though we omit them when all
variables within an equation belong to the same stage.
Drawing inspiration from the U-Net architecture (Ronneberger, Fischer, and Brox 2015), H-Net progressively compresses
input sequences into fewer vectors with richer semantic embeddings through a chunking layer, processes these representa-
tions in the main network, then decompresses the sequence
```

### `hnet-v2:s3.1:c0003` p.12 §3.1 Language Modeling [ok]
```
data, as the model continuously refines its chunking strategy.
Downstream Evaluations.
Table 2 presents zero-shot accuracy across diverse downstream benchmarks (Paperno et al.
2016; Zellers et al. 2019; Bisk et al. 2020; Clark, Cowhey, et al. 2018; Sakaguchi et al. 2021; Mihaylov et al. 2018) using
lm-evaluation-harness (Gao, Tow, et al. 2024) for models at Large and XL scales. SpaceByte++, H-Net (space), and
H-Net (1-stage) all have similar performance to the BPE Transformer at Large scale, and slightly outperform it at the XL
scale, consistent with their close training curves (and possibly reflecting some noise in the evaluations).
H-Net (2-stage) consistently achieves the highest performance across most tasks, outperforming 2.2% and 2.6%
over the Transformer baseline at Large and XL scales respectively. Notably, the Large H-Net (2-stage) matches the average
downstream performance of
```

## moshi (258 chunks)

### `moshi-v1:s3.3.1:c0006` p.9 §3.3.1 Architecture [ok]
```
provide the codec with bitrate scalability. We moreover follow the obser-
vation of
Kumar et al. (2023) that not applying quantization with a certain probability
during training improves audio quality. More precisely, we only apply quantization 50% of
the time, on a per-sequence basis, during training. Unlike Kumar et al. (2023), this means
passing unquantized embeddings to the decoder, rather than passing embeddings quantized
with all quantizers. Table 3 shows that this significantly improves objective quality metrics,
while human evaluations are not conclusive. Across our experiments, we make the somehow
counter-intuitive observation that this gain gets more significant as we lower the bitrate.
Adversarial-only training.
As a baseline, we train Mimi with the same combination of
reconstruction and adversarial losses as D´efossez et al. (2023), namely a multi-scale mel-
spectrogram
```

### `moshi-v1:s7:c0046` p.41 §7 Conclusion [ok]
```
in the dataset, as eval-
uated in Section 6.2.
2. Indexing solution. By collecting signatures of samples at generation time, we can find
if some content has been generated by our demo or not by direct retrieval.
Our audio matching solution is inspired by the work of Wang (2003), as it offers a good
trade-off between efficiency and effectiveness. This method is a retrieval system: given a
query, it detects the similar audio in a pre-indexed dataset. In our case, the signature design
favors the de-duplication use-case, which needs to be more efficient: Formally, we need to
compare every audio of the dataset with the whole dataset, which raises efficiency issues.
The signature extraction is described below.
Constellation map
The first step to produce the signatures involves computing a set
of keypoint referred to as a constellation map. Our procedure is inspired by Wang (2003)
and
```

### `moshi-v1:s3.2.1:c0000` p.7 §3.2.1 Architecture [ok]
```
Helium is an autoregressive language model, based on the Transformer architecture (Vaswani
et al., 2017). Following previous work in this area, we make the following changes to the
original architecture: First, we use RMS normalization (Zhang and Sennrich, 2019) at the
input of the attention blocks, the feed-forward blocks and the output linear layer of the
model. We use rotation positional embeddings (Su et al., 2024, RoPE), a context length
of 4,096 tokens and FlashAttention (Dao et al., 2022) for efficient training. Finally, we
change the architecture of the feed-forward blocks and use Gated Linear Units (Shazeer,
2020), with the SiLU activation as a gating function (Hendrycks and Gimpel, 2016b). Our
tokenizer is based on the unigram model from SentencePiece (Kudo and Richardson, 2018),
and contains 32,000 elements mostly targeting English. We split all numbers into single
digits,
```

### `moshi-v1:s3.4.3:c0001` p.14 §3.4.3 Multi-stream modeling [ok]
```
delay τ = 1, e.g. the input of the Temporal Transformer for this step.
Tokens are predicted from bottom to top in the Depth Transformer. At inference time,
tokens under the dashed line (corresponding to Moshi) are sampled, while those above are
fed from the user. This design allows for our model to handle overlapping speech turns.
(At,q) and (A′
t,q), we simply apply the acoustic delay to both, and concatenate them into V ,
extending Equation 4. In practice, A will correspond to Moshi, while A′ models the user.
```

### `moshi-v1:s5.4:c0000` p.26 §5.4 Audio language modeling [caption]
```
Metrics.
We first measure the ability of Moshi to model speech sequences when being
trained for next token prediction on large scale audio data. To do so, we rely on “textless
NLP” (Lakhotia et al., 2021) metrics that evaluate an audio language model’s linguistic
knowledge by comparing likelihoods of positive and negative speech examples represented
Moshi: a speech-text foundation model for real-time dialogue
Table 7: Performance of audio and text language modeling. We report accuracies
based on scoring with negative log-likelihood, normalized by sequence length. MMLU is
evaluated in a 5-shot setting. Reusing the terminology of Nguyen et al. (2024), ∅represents
unsupported modalities while - represents unreported numbers.
Audio metrics
Text metrics
Model
sWUGGY
sBLIMP
sTopic-StoryCloze
sStoryCloze
MMLU
Audio only - Cold Start
GSLM (Lakhotia et al., 2021)
64.8
54.2
66.6
53.3
AudioLM
```

### `moshi-v1:s3.2.1:c0001` p.7 §3.2.1 Architecture [ok]
```
model from SentencePiece (Kudo and Richardson, 2018),
and contains 32,000 elements mostly targeting English. We split all numbers into single
digits, and use byte-backoff to ensure that our tokenizer does not lose information. We
train the model with the AdamW (Loshchilov and Hutter, 2017) optimizer, with a fixed
learning rate followed by a cosine learning rate decay (Loshchilov and Hutter, 2016).
```

### `moshi-v1:s7:c0032` p.41 §7 Conclusion [ok]
```
Chowdhery, Roman Ring, Stephen Spencer, Eren Sezener, and et al. Gemini
1.5: Unlocking multimodal understanding across millions of tokens of context. CoRR,
abs/2403.05530, 2024. doi: 10.48550/ARXIV.2403.05530. 4
Paul K. Rubenstein, Chulayuth Asawaroengchai, Duc Dung Nguyen, Ankur Bapna, Zal´an
Borsos, F´elix de Chaumont Quitry, Peter Chen, Dalia El Badawy, Wei Han, Eu-
gene Kharitonov, Hannah Muckenhirn, Dirk Padfield, James Qin, Danny Rozenberg,
Tara N. Sainath, Johan Schalkwyk, Matthew Sharifi, Michelle Tadmor Ramanovich,
Marco Tagliasacchi, Alexandru Tudor, Mihajlo Velimirovic, Damien Vincent, Jiahui Yu,
Yongqiang Wang, Vicky Zayats, Neil Zeghidour, Yu Zhang, Zhishuai Zhang, Lukas Zilka,
and Christian Havnø Frank. Audiopalm: A large language model that can speak and
listen. CoRR, abs/2306.12925, 2023. doi: 10.48550/ARXIV.2306.12925. 4, 5
Alexandre Sablayrolles, Matthijs Douze,
```

### `moshi-v1:s2:c0012` p.4 §2 Related Work [ok]
```
models user and system speech as separate audio token streams and pro-
poses a Siamese architecture to process both streams jointly. While dGSLM is full-duplex,
it remains a proof-of-concept: it does not run in an online fashion, it does not benefit from
the knowledge of a text language model, and it does not model acoustic information as it
only models semantic tokens. Moshi addresses these limitations altogether: by modeling
two streams of semantic and acoustic tokens hierarchically, Moshi is full duplex and can
exploit all the information from the user (linguistic and non-linguistic) while producing
speech in real time. Thanks to text pretraining and Inner Monologue, Moshi benefits from
the knowledge of its Helium backbone. Finally, as the model produces acoustic tokens along
with text and semantic tokens, it can generate an arbitrary range of emotions, voices and
acoustic
```

### `moshi-v1:s5.3:c0005` p.25 §5.3 Ablations on generative modeling [ok]
```
how helpful modeling text tokens as a prefix to audio tokens with Inner Monologue is, even
in an audio-to-audio setting. Given the positive impact of depthwise parametrization and
a weight of 100 for the semantic token, both are used in all our subsequent experiments, as
well as our final training procedure. Moreover, and as described in Table 1, we settle on a
theoretical latency of 160ms by pretraining Moshi with an acoustic delay of 2 and finetuning
it with an acoustic delay of 1.
```

### `moshi-v1:s2:c0010` p.4 §2 Related Work [caption]
```
speech and text tokens in parallel to reduce
this latency, however it reduces the quality of answers, and the model still relies on ASR,
which removes paralinguistic information. More importantly, these models cannot handle
full-duplex communication, where there is no boundary between speaker turns, as any side
of the conversation can be active at any time. An attempt at modeling these dynamics has
Moshi: a speech-text foundation model for real-time dialogue
Figure 1: Overview of Moshi. Moshi is a speech-text foundation model which enables
real-time spoken dialogue. The main components of Moshi’s architecture are: a bespoke
text language model backbone (Helium, see Section 3.2); a neural audio codec with residual
vector quantization and with semantic knowledge distilled from a self-supervised speech
model (Mimi, Section 3.3); the streaming, hierarchical generation of semantic and
```
