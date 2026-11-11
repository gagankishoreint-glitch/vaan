# Random chunks per paper (eyeball these)

## attention (83 chunks)

### `attn-v7:s4:c0006` p.6 §4 Why Self-Attention [short]
```
in the appendix. Not only do individual attention
heads clearly learn to perform different tasks, many appear to exhibit behavior related to the syntactic
and semantic structure of the sentences.
```

### `attn-v7:s3.2.1:c0000` p.4 §3.2.1 Scaled Dot-Product Attention [equation]
```
We call our particular attention "Scaled Dot-Product Attention" (Figure 2). The input consists of
queries and keys of dimension dk, and values of dimension dv. We compute the dot products of the
query with all keys, divide each by √dk, and apply a softmax function to obtain the weights on the
values.
In practice, we compute the attention function on a set of queries simultaneously, packed together
into a matrix Q. The keys and values are also packed together into matrices K and V . We compute
the matrix of outputs as:
Attention(Q, K, V ) = softmax(QKT
√dk
(1)
The two most commonly used
```

### `attn-v7:s6.1:c0001` p.8 §6.1 Machine Translation [ok]
```
models.
On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score of 41.0,
outperforming all of the previously published single models, at less than 1/4 the training cost of the
previous state-of-the-art model. The Transformer (big) model trained for English-to-French used
dropout rate Pdrop = 0.1, instead of 0.3.
For the base models, we used a single model obtained by averaging the last 5 checkpoints, which
were written at 10-minute intervals. For the big models, we averaged the last 20 checkpoints. We
used beam search with a beam size of 4 and length penalty α
```

### `attn-v7:s1:c0001` p.2 §1 Introduction [ok]
```
the input and output
sequences. Aligning the positions to steps in computation time, they generate a sequence of hidden
states ht, as a function of the previous hidden state ht−1 and the input for position t. This inherently
sequential nature precludes parallelization within training examples, which becomes critical at longer
sequence lengths, as memory constraints limit batching across examples. Recent work has achieved
significant improvements in computational efficiency through factorization tricks [21] and conditional
computation [32], while also improving model performance in case of the
```

### `attn-v7:s2:c0000` p.2 §2 Background [ok]
```
The goal of reducing sequential computation also forms the foundation of the Extended Neural GPU
[16], ByteNet [18] and ConvS2S [9], all of which use convolutional neural networks as basic building
block, computing hidden representations in parallel for all input and output positions. In these models,
the number of operations required to relate signals from two arbitrary input or output positions grows
in the distance between positions, linearly for ConvS2S and logarithmically for ByteNet. This makes
it more difficult to learn dependencies between distant positions [12]. In the Transformer
```

### `attn-v7:s7:c0006` p.10 §7 Conclusion [ok]
```
Recognition, pages 770–778, 2016.
[12] Sepp Hochreiter, Yoshua Bengio, Paolo Frasconi, and Jürgen Schmidhuber. Gradient flow in
recurrent nets: the difficulty of learning long-term dependencies, 2001.
[13] Sepp Hochreiter and Jürgen Schmidhuber. Long short-term memory. Neural computation,
9(8):1735–1780, 1997.
[14] Zhongqiang Huang and Mary Harper. Self-training PCFG grammars with latent annotations
across languages. In Proceedings of the 2009 Conference on Empirical Methods in Natural
Language Processing, pages 832–841. ACL, August 2009.
[15] Rafal Jozefowicz, Oriol Vinyals, Mike Schuster,
```

### `attn-v7:s2:c0003` p.2 §2 Background [ok]
```
the Transformer is the first transduction model relying
entirely on self-attention to compute representations of its input and output without using sequence-
aligned RNNs or convolution. In the following sections, we will describe the Transformer, motivate
self-attention and discuss its advantages over models such as [17, 18] and [9].
```

### `attn-v7:s5.4:c0000` p.7 §5.4 Regularization [numeric_dense,caption]
```
We employ three types of regularization during training:
Table 2: The Transformer achieves better BLEU scores than previous state-of-the-art models on the
English-to-German and English-to-French newstest2014 tests at a fraction of the training cost.
Model
BLEU
Training Cost (FLOPs)
EN-DE
EN-FR
EN-DE
EN-FR
ByteNet [18]
23.75
Deep-Att + PosUnk [39]
39.2
1.0 · 1020
GNMT + RL [38]
24.6
39.92
2.3 · 1019
1.4 · 1020
ConvS2S [9]
25.16
40.46
9.6 · 1018
1.5 · 1020
MoE [32]
26.03
40.56
2.0 · 1019
1.2 · 1020
Deep-Att + PosUnk Ensemble [39]
40.4
8.0 · 1020
GNMT + RL Ensemble [38]
26.30
41.16
1.8 ·
```

### `attn-v7:s7:c0012` p.10 §7 Conclusion [ok]
```
Linguistics and 44th Annual Meeting of the ACL, pages 433–440. ACL, July
2006.
[30] Ofir Press and Lior Wolf. Using the output embedding to improve language models. arXiv
preprint arXiv:1608.05859, 2016.
[31] Rico Sennrich, Barry Haddow, and Alexandra Birch. Neural machine translation of rare words
with subword units. arXiv preprint arXiv:1508.07909, 2015.
[32] Noam Shazeer, Azalia Mirhoseini, Krzysztof Maziarz, Andy Davis, Quoc Le, Geoffrey Hinton,
and Jeff Dean. Outrageously large neural networks: The sparsely-gated mixture-of-experts
layer. arXiv preprint arXiv:1701.06538, 2017.
[33]
```

### `attn-v7:s1:c0002` p.2 §1 Introduction [ok]
```
tricks [21] and conditional
computation [32], while also improving model performance in case of the latter. The fundamental
constraint of sequential computation, however, remains.
Attention mechanisms have become an integral part of compelling sequence modeling and transduc-
tion models in various tasks, allowing modeling of dependencies without regard to their distance in
the input or output sequences [2, 19]. In all but a few cases [27], however, such attention mechanisms
are used in conjunction with a recurrent network.
In this work we propose the Transformer, a model architecture
```

## hnet (277 chunks)

### `hnet-v2:s5:c0095` p.23 §5 Conclusion [caption,caption_lead]
```
Figure 13: Compression Methods in chunking layer. Default: H-Net’s Downsample operation (left-a). Max/Mean:
Channel-wise max and mean pooling within boundaries (left-b). XAttn: Cross-attention pooling within boundaries (left-c).
+Res: Adds boundary vector residuals to compressed outputs.
where 𝑁GPT is the average number of bytes per token of training dataset, which is 4.6 for the GPT-2 tokenizer on
FineWeb-Edu.
We note that such principles for optimizing signal propagation as neural network hyperparameters change is an active
area of research, and our scaling factors are just heuristics that
```

### `hnet-v2:s3.1:c0020` p.12 §3.1 Language Modeling [short]
```
based on content and context. In
particular, it often still chunks in between semantic words even if the space is removed.
```

### `hnet-v2:s1:c0015` p.1 §1 Introduction [ok]
```
representations.
Recursive H-Nets represent a new class of foundation model architectures that not only overcome tokenization, but discover
and operate over abstractions learned from raw data, leading to higher-quality models with less pre-processing. Iterating the
1-stage H-Net to 2 hierarchical stages further improves its capabilities and strongly outperforms all baselines, with steeper
training curves and better scaling with data. A byte-level 2-stage H-Net overtakes the perplexity of a strong tokenized
Transformer after just 30B training bytes, with the gap widening throughout training,
```

### `hnet-v2:s2.2:c0005` p.6 §2.2 Dynamic Chunking (DC) [ok]
```
flow during backpropagation. We introduce the smoothing module as a technique
to address this problem. As illustrated in Figure 1-(c), this component transforms discrete chunking operations into
̂#duct!
#…ne
#du
#pro
!new_
!duct!
̂#new_
#pro
#duct!
Upper Stages
Upper Stages
Upper Stages
(a) Oracle Boundaries
(b) w/o Smoothing Module
(c) w/ Smoothing Module
!ne
!new_
!du
!duct!
!pro
!ne
!new_
!du
!duct!
!pro
!pro
#new_
#duct!
#ne
#du
#pro
#produ
#new_
#neà
n e w _ p r o d u c t ! _
… n e w _ p r o d u c t !
… n e w _ p r o d u c t !
n e w _ p r o d u c t ! _
n e w _ p r o d u c t ! _
… n e w _
```

### `hnet-v2:s5:c0058` p.23 §5 Conclusion [caption]
```
this delineation because it marks an important
difference in motivation that influences design considerations and downstream evaluations.
• Appendix A.3 mentions other works in non-language modalities related to tokenization.
We summarize our discussion on tokenizer-free architectures in Table 6.
A.1
Autoregressive Tokenizer-free Architectures
As outlined in Section 1, prior work on autoregressive tokenizers for architectures can be divided into four categories:
1. Non-hierarchical isotropic architectures.
2. Hierarchical architectures with static chunking strategies, where chunk boundaries
```

### `hnet-v2:s5:c0050` p.23 §5 Conclusion [ok]
```
Infinite-width Neural Networks”. In: arXiv preprint arXiv:2011.14522
(2020).
[107]
Songlin Yang, Jan Kautz, and Ali Hatamizadeh. “Gated Delta Networks: Improving Mamba2 with Delta Rule”. In:
The Thirteenth International Conference on Learning Representations (ICLR). 2025.
[108]
Songlin Yang, Bailin Wang, Yikang Shen, Rameswar Panda, and Yoon Kim. “Gated Linear Attention Transformers
with Hardware-Efficient Training”. In: The International Conference on Machine Learning (ICML). 2024.
[109]
Songlin Yang, Bailin Wang, Yu Zhang, Yikang Shen, and Yoon Kim. “Parallelizing Linear Transformers with
```

### `hnet-v2:s2.1:c0010` p.4 §2.1 Architectural Overview [ok]
```
experiments. However, the modular design also allows straightforward substitution
with alternative architectures (e.g., a state space model, hybrid, or H-Net itself) as explored in our ablations.
Architectural Guidelines.
Compared to standard isotropic models, the H-Net’s structure introduces several new
dimensions of architectural parameters to balance the parameter/compute allocation to each network. To simplify the
search space, we follow a few general guidelines.
7We also sometimes refer to it as a probability—it is interpreted as such in Appendix F—although we do not use it as a formal
```

### `hnet-v2:s3.2:c0013` p.15 §3.2 Alternate Language Datasets [short]
```
to isotropic models with just 3.6× the amount of data, a finding that holds for both choices
of main network architecture.
```

### `hnet-v2:s2.2:c0007` p.6 §2.2 Dynamic Chunking (DC) [ok]
```
meaningful units. (b) Suboptimal chunking without a smoothing module. This creates
misalignment during upsampling, causing information from incorrect contexts to propagate. (c) Improved decompression
with a smoothing module, where low-confidence chunks are interpolated with weighted combinations of previous chunks,
correcting the shaded regions. In panels (b) and (c), we interpret low-confidence boundaries cause the encoder network to
embed broader contexts at subsequent positions. Specifically, the vectors at _ and ! encode new_ and duct!, respectively
(instead of w_ and ct!).
differentiable
```

### `hnet-v2:s5:c0053` p.23 §5 Conclusion [ok]
```
Ji Pei. OpenCSG Chinese Corpus: A Series of High-
quality Chinese Datasets for LLM Training. 2025. arXiv: 2501.08197 [cs.CL]. url: https://arxiv.org/abs/
2501.08197.
[114]
Rowan Zellers, Ari Holtzman, Yonatan Bisk, Ali Farhadi, and Yejin Choi. “HellaSwag: Can a Machine Really Finish
Your Sentence?” In: Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics. 2019.
[115]
Biao Zhang and Rico Sennrich. “Root Mean Square Layer Normalization”. In: Advances in Neural Information
Processing Systems 32 (2019).
Related Work
The fundamental challenge of transforming raw
```

## moshi (384 chunks)

### `moshi-v1:s2:c0011` p.4 §2 Related Work [ok]
```
and first produce
an utterance as text tokens, subsequently used as a prefix to generate speech. In this work,
we propose Inner Monologue as a main architectural and training component to combine
aligned text and speech data. Inner Monologue decomposes speech into a chain of text, se-
mantic and acoustic tokens, and predicts this structured sequence in a hierarchical manner.
Unlike Spirit-LM, this allows representing all utterances both as text and speech, rather than
switching between modalities; In addition, the integration of acoustic tokens into the same
generative model enables
```

### `moshi-v1:s7:c0036` p.41 §7 Conclusion [ok]
```
Computational Linguistics, 9:1336–1354, 2021. 4, 23, 26, 27, 29
Doyup Lee, Chiheon Kim, Saehoon Kim, Minsu Cho, and Wook-Shin Han. Autoregressive
image generation using residual quantization. In IEEE/CVF Conference on Computer
Vision and Pattern Recognition, CVPR 2022, New Orleans, LA, USA, June 18-24, 2022,
2022. 4, 13, 14
Jean-Marie Lemercier, Simon Rouard, Jade Copet, Yossi Adi, and Alexandre D´efossez. An
independence-promoting loss for music generation with language models. In ICML, 2024.
Haohe Liu, Ke Chen, Qiao Tian, Wenwu Wang, and Mark D Plumbley. AudioSR: Versatile
audio
```

### `moshi-v1:s3.3.1:c0005` p.9 §3.3.1 Architecture [ok]
```
we use LayerScale (Touvron et al., 2021),
with initialization of the diagonal values at 0.01. Both Transformers use causal masking,
which preserves the compatibility of the whole architecture with streaming inference. Both
Transformers prove to be useful with regard to perceived audio quality, while Transformer
in the encoder also improves the distillation of semantic information described below (see
Table 3 for ablation studies).
Causality and streaming.
With the mentioned hyper-parameters, Mimi is causal and
can be used in a streaming fashion, both for encoding and decoding. Both its
```

### `moshi-v1:s4.3:c0001` p.18 §4.3 Speech-Text Instruct data [caption]
```
realistic interactions between a speech-
based AI model and a user. We then synthesize them with our multi-stream streaming
TTS described in Appendix C, leading to more than 20k hours of synthetic speech data.
To give Moshi its own consistent voice, we also condition the TTS engine on the voice of a
single actor, who recorded monologues covering more than 70 speaking styles, as listed in
Table 19. Experiments on voice consistency reported in Section 6.3 show that simply using
a consistent voice for Moshi during instruction tuning is enough to guarantee almost surely
that it does not use
```

### `moshi-v1:s7:c0069` p.41 §7 Conclusion [ok]
```
duplicates to avoid overfitting
and the regurgitation of audio content that is over-represented in the dataset, as eval-
uated in Section 6.2.
2. Indexing solution. By collecting signatures of samples at generation time, we can find
if some content has been generated by our demo or not by direct retrieval.
Our audio matching solution is inspired by the work of Wang (2003), as it offers a good
trade-off between efficiency and effectiveness. This method is a retrieval system: given a
query, it detects the similar audio in a pre-indexed dataset. In our case, the signature design
favors the
```

### `moshi-v1:s7:c0068` p.41 §7 Conclusion [numeric_dense]
```
Quantization
Transformer
Transformer
WavLM
Split
ABX (↓)
VisQOL (↑)
MOSNet (↑)
Rate
in encoder
in decoder
distillation
quantizer
31.3%
2.37
2.85
31.4%
2.30
2.82
27.5%
2.30
2.93
29.0%
2.25
2.94
29.1%
2.65
2.86
27.4%
2.69
2.83
23.6%
2.72
2.89
23.3%
2.82
2.89
6.5%
2.13
2.87
10.8%
2.68
2.84
8.1%
2.49
2.71
8.0%
2.36
2.88
8.1%
2.72
2.89
Appendix B. Audio matching and deduplication
We have developed an audio matching system, whose objective is twofold:
1. Deduplication of source content. Removing frequent duplicates to avoid overfitting
and the regurgitation of audio content that is over-represented
```

### `moshi-v1:s7:c0045` p.41 §7 Conclusion [ok]
```
23, 31
Alec Radford, Karthik Narasimhan, Tim Salimans, Ilya Sutskever, et al. Improving language
understanding by generative pre-training. Technical report, OpenAI, 2018. 4
Alec Radford, Jeff Wu, Rewon Child, David Luan, Dario Amodei, and Ilya Sutskever.
Language models are unsupervised multitask learners. Technical report, OpenAI, 2019.
Alec Radford, Jong Wook Kim, Tao Xu, Greg Brockman, Christine McLeavey, and Ilya
Sutskever. Robust speech recognition via large-scale weak supervision. In Andreas Krause,
Emma Brunskill, Kyunghyun Cho, Barbara Engelhardt, Sivan Sabato, and Jonathan
Scarlett,
```

### `moshi-v1:s2:c0012` p.4 §2 Related Work [ok]
```
modalities; In addition, the integration of acoustic tokens into the same
generative model enables generating arbitrary voices and conditions, rather than a single
speaker. Besides, this hierarchical modeling described in Section 3.4.4 allows decomposing
the generation task without increasing the sequence length of the Transformer (Vaswani
et al., 2017) outputs, unlike Chain-of-Modality. Moreover, Inner Monologue decomposes
speech on a per-frame basis, which means that each prediction step outputs a speech frame.
This is unlike Spectron which requires generating a complete sequence as text
```

### `moshi-v1:s7:c0042` p.41 §7 Conclusion [ok]
```
Rana Ali Amjad, Yelysei Bondarenko, Mart van Baalen,
and Tijmen Blankevoort. A white paper on neural network quantization, 2021. 32
Tu Anh Nguyen, Eugene Kharitonov, Jade Copet, Yossi Adi, Wei-Ning Hsu, Ali Elkahky,
Paden Tomasello, Robin Algayres, Benoˆıt Sagot, Abdelrahman Mohamed, and Emmanuel
Dupoux. Generative spoken dialogue language modeling. Transactions of the Association
for Computational Linguistics, 11:250–266, 2023. doi: 10.1162/tacl a 00545. 6, 30, 31
Tu Anh Nguyen, Benjamin Muller, Bokai Yu, Marta R. Costa-juss`a, Maha Elbayad, Sravya
Popuri, Paul-Ambroise Duquenne, Robin
```

### `moshi-v1:s7:c0046` p.41 §7 Conclusion [ok]
```
Krause,
Emma Brunskill, Kyunghyun Cho, Barbara Engelhardt, Sivan Sabato, and Jonathan
Scarlett, editors, International Conference on Machine Learning, ICML 2023, 23-29 July
2023, Honolulu, Hawaii, USA, volume 202 of Proceedings of Machine Learning Research,
pages 28492–28518. PMLR, 2023. 4, 15, 17, 25
Machel Reid, Nikolay Savinov, Denis Teplyashin, Dmitry Lepikhin, Timothy P. Lillicrap,
Jean-Baptiste Alayrac, Radu Soricut, Angeliki Lazaridou, Orhan Firat, Julian Schrit-
twieser, Ioannis Antonoglou, Rohan Anil, Sebastian Borgeaud, Andrew M. Dai, Katie
Millican, Ethan Dyer, Mia Glaese, Thibault
```
