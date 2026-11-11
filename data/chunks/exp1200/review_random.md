# Random chunks per paper (eyeball these)

## attention (47 chunks)

### `attn-v7:s4:c0000` p.6 §4 Why Self-Attention [ok]
```
In this section we compare various aspects of self-attention layers to the recurrent and convolu-
tional layers commonly used for mapping one variable-length sequence of symbol representations
(x1, ..., xn) to another sequence of equal length (z1, ..., zn), with xi, zi ∈Rd, such as a hidden
layer in a typical sequence transduction encoder or decoder. Motivating our use of self-attention we
consider three desiderata.
One is the total computational complexity per layer. Another is the amount of computation that can
be parallelized, as measured by the minimum number of sequential operations required.
The third is the path length between long-range dependencies in the network. Learning long-range
dependencies is a key challenge in many sequence transduction tasks. One key factor affecting the
ability to learn such dependencies is the length of the paths forward and backward signals have to
traverse in the network. The shorter these paths between any combination of positions in the input
and output sequences, the easier it is to learn long-range dependencies [12]. Hence we also compare
the maximum path length between any two input and output positions in networks composed of
```

### `attn-v7:s3.1:c0001` p.3 §3.1 Encoder and Decoder Stacks [ok]
```
also modify the self-attention
sub-layer in the decoder stack to prevent positions from attending to subsequent positions. This
masking, combined with fact that the output embeddings are offset by one position, ensures that the
predictions for position i can depend only on the known outputs at positions less than i.
```

### `attn-v7:s5.2:c0000` p.7 §5.2 Hardware and Schedule [ok]
```
We trained our models on one machine with 8 NVIDIA P100 GPUs. For our base models using
the hyperparameters described throughout the paper, each training step took about 0.4 seconds. We
trained the base models for a total of 100,000 steps or 12 hours. For our big models,(described on the
bottom line of table 3), step time was 1.0 seconds. The big models were trained for 300,000 steps
(3.5 days).
```

### `attn-v7:s7:c0005` p.10 §7 Conclusion [ok]
```
2015.
[25] Mitchell P Marcus, Mary Ann Marcinkiewicz, and Beatrice Santorini. Building a large annotated
corpus of english: The penn treebank. Computational linguistics, 19(2):313–330, 1993.
[26] David McClosky, Eugene Charniak, and Mark Johnson. Effective self-training for parsing. In
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
[31] Rico Sennrich, Barry Haddow, and Alexandra Birch. Neural machine translation of
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
sequence lengths, as memory constraints limit batching across examples. Recent work has achieved
significant improvements in computational efficiency through factorization tricks [21] and conditional
computation [32], while also improving model performance in case of the latter. The fundamental
constraint of sequential computation, however, remains.
Attention mechanisms have
```

### `attn-v7:s1:c0001` p.2 §1 Introduction [ok]
```
[21] and conditional
computation [32], while also improving model performance in case of the latter. The fundamental
constraint of sequential computation, however, remains.
Attention mechanisms have become an integral part of compelling sequence modeling and transduc-
tion models in various tasks, allowing modeling of dependencies without regard to their distance in
the input or output sequences [2, 19]. In all but a few cases [27], however, such attention mechanisms
are used in conjunction with a recurrent network.
In this work we propose the Transformer, a model architecture eschewing recurrence and instead
relying entirely on an attention mechanism to draw global dependencies between input and output.
The Transformer allows for significantly more parallelization and can reach a new state of the art in
translation quality after being trained for as little as twelve hours on eight P100 GPUs.
```

### `attn-v7:s6.3:c0001` p.9 §6.3 English Constituency Parsing [caption]
```
parameters
remained unchanged from the English-to-German base translation model. During inference, we
Table 4: The Transformer generalizes well to English constituency parsing (Results are on Section 23
of WSJ)
Parser
Training
WSJ 23 F1
Vinyals & Kaiser el al. (2014) [37]
WSJ only, discriminative
88.3
Petrov et al. (2006) [29]
WSJ only, discriminative
90.4
Zhu et al. (2013) [40]
WSJ only, discriminative
90.4
Dyer et al. (2016) [8]
WSJ only, discriminative
91.7
Transformer (4 layers)
WSJ only, discriminative
91.3
Zhu et al. (2013) [40]
semi-supervised
91.3
Huang & Harper (2009) [14]
semi-supervised
91.3
McClosky et al. (2006) [26]
semi-supervised
92.1
Vinyals & Kaiser el al. (2014) [37]
semi-supervised
92.1
Transformer (4 layers)
semi-supervised
92.7
Luong et al. (2015) [23]
multi-task
93.0
Dyer et al. (2016) [8]
generative
93.3
increased the maximum output length to input length + 300. We used a beam size of 21 and α = 0.3
for both WSJ only and the semi-supervised setting.
Our results in Table 4 show that despite the lack of task-specific tuning our model performs sur-
prisingly well, yielding better results than all previously reported models with the exception of the
Recurrent
```

### `attn-v7:s2:c0001` p.2 §2 Background [ok]
```
of the sequence. Self-attention has been
used successfully in a variety of tasks including reading comprehension, abstractive summarization,
textual entailment and learning task-independent sentence representations [4, 27, 28, 22].
End-to-end memory networks are based on a recurrent attention mechanism instead of sequence-
aligned recurrence and have been shown to perform well on simple-language question answering and
language modeling tasks [34].
To the best of our knowledge, however, the Transformer is the first transduction model relying
entirely on self-attention to compute representations of its input and output without using sequence-
aligned RNNs or convolution. In the following sections, we will describe the Transformer, motivate
self-attention and discuss its advantages over models such as [17, 18] and [9].
```

### `attn-v7:s5:c0000` p.7 §5 Training [short]
```
This section describes the training regime for our models.
```

### `attn-v7:s7:c0001` p.10 §7 Conclusion [ok]
```
and evaluate our models is available at https://github.com/
tensorflow/tensor2tensor.
Acknowledgements
We are grateful to Nal Kalchbrenner and Stephan Gouws for their fruitful
comments, corrections and inspiration.
References
[1] Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. arXiv preprint
arXiv:1607.06450, 2016.
[2] Dzmitry Bahdanau, Kyunghyun Cho, and Yoshua Bengio. Neural machine translation by jointly
learning to align and translate. CoRR, abs/1409.0473, 2014.
[3] Denny Britz, Anna Goldie, Minh-Thang Luong, and Quoc V. Le. Massive exploration of neural
machine translation architectures. CoRR, abs/1703.03906, 2017.
[4] Jianpeng Cheng, Li Dong, and Mirella Lapata. Long short-term memory-networks for machine
reading. arXiv preprint arXiv:1601.06733, 2016.
[5] Kyunghyun Cho, Bart van Merrienboer, Caglar Gulcehre, Fethi Bougares, Holger Schwenk,
and Yoshua Bengio. Learning phrase representations using rnn encoder-decoder for statistical
machine translation. CoRR, abs/1406.1078, 2014.
[6] Francois Chollet. Xception: Deep learning with depthwise separable convolutions. arXiv
preprint arXiv:1610.02357, 2016.
[7] Junyoung Chung, Çaglar Gülçehre, Kyunghyun
```

## hnet (138 chunks)

### `hnet-v2:s2.1:c0002` p.4 §2.1 Architectural Overview [ok]
```
are defined as:
(𝑥𝑠+1, 𝑝𝑠) = Chunk( ˆ𝑥𝑠),
(2)
𝑧𝑠= Dechunk(ˆ𝑧𝑠+1, 𝑝𝑠) + Linear( ˆ𝑥𝑠).
(3)
The initial input to the model is 𝑥0 ∈R𝐿0×𝐷0 where 𝐿0 is the input sequence length and 𝐷0 is the embedding dimension.
Intuitively, 𝑝𝑠∈[0, 1]𝐿𝑠represents the chunking router’s confidence that the token should be passed into the main stage. 7
This value is essential for both the chunk (Section 2.2.1) and dechunk operations (Section 2.2.2).
2.1.2
Design Principles
Encoder and Decoder Networks.
The encoder and decoder networks in H-Net face unique design constraints due
to their dual objectives and computational requirements. Each encoder must simultaneously (i) preserve fine-grained
information for transmission to its corresponding decoder through residual connections (3), and (ii) compress inputs into
chunks of richer representations for the main network. The decoder, in turn, must effectively combine coarse-grained
representations from the main network with fine-grained details from the encoder residuals.
Importantly, both encoders and decoders operate on uncompressed sequences, making computational efficiency a significant
design constraint that shapes our architectural choices. Recent studies
```

### `hnet-v2:s5:c0048` p.23 §5 Conclusion [ok]
```
that can likely be improved.
Additional Experimental Setup Details
D.1
Robustness Score
We introduce a metric called the robustness score to measure the robustness of a model’s performance to textual perturbations,
defined for Hellaswag as follows:
robustness score B 100 ·
perturbed accuracy −0.25
max(unperturbed accuracy −0.25, 0) .
This score measures the percentage of original (unperturbed) performance that is captured by the model in the perturbed
setting. We subtract by 0.25 as HellaSwag is multiple choice with 4 options, thus a model that scores 0.25 in the perturbed
setting should be considered to have lost all of its original capability.
Additional Ablation Studies
E.1
Different Downsampling Methods in the Chunking Layer
Given the dynamically determined boundaries from the boundary predictor, we explore various compression strategies in
the chunking layer. We compare the default Downsample operation of H-Net (see Section 2.2.1) against three alternatives
(see Figure 13-left): channel-wise max/mean pooling and cross-attention, all applied to vectors within the same boundary.
Despite its simple design, the default compression in H-Net performs on-par with the other variants
```

### `hnet-v2:s3.2:c0000` p.15 §3.2 Alternate Language Datasets [caption]
```
20B
30B
40B
50B
60B
70B
80B
90B
100B
Total Training Bytes
0.74
0.76
0.78
0.80
0.82
0.84
0.86
0.88
0.90
Validation Bits-per-byte
Chinese (F.-Edu-Chinese-V2.1)
20B
30B
40B
50B
60B
70B
80B
Total Training Bytes
0.36
0.38
0.40
0.42
0.44
Code (Pile Github)
H-Net (2-stage)
H-Net (space)
(BPE) Transformer
Figure 5: Validation Bits-per-byte (BPB) throughout training on Chinese language and code modeling. H-Net
(space) and H-Net (2-stage) are byte-level, while the Transformers use the Llama-3 tokenizer which was designed for
multilingual. H-Net clearly outperforms both Transformer and H-Net (space) on Chinese language modeling, which
does not have space-like segmentation cues, with lower BPB than H-Net (space) throughout training and crossing over
with Transformer after around 25B bytes. On code, both H-Net (2-stage) and H-Net (space) significantly outperform BPE
Transformer. Final post-decay results can be found in Table 4.
H-Net can operate on raw data without the need for handcrafted features (whether vocabulary or deliniation cues); it
therefore provides a natural architecture that can operate naturally on any language.
Experimental setup for Chinese and code.
On Chinese and code, we
```

### `hnet-v2:s1:c0007` p.1 §1 Introduction [ok]
```
Crucially, because H-Net is fully end-to-end, it can be iterated
recursively: the main network can itself be an H-Net. Intuitively, more stages of chunking represent higher order
meanings; just as characters can be combined into words, words can be combined into clauses, sentences, and beyond.
Iterating the hierarchy should therefore lead to even more efficient use of compute and parameters, and more effective
reasoning over compressed representations.
Recursive H-Nets represent a new class of foundation model architectures that not only overcome tokenization, but discover
and operate over abstractions learned from raw data, leading to higher-quality models with less pre-processing. Iterating the
1-stage H-Net to 2 hierarchical stages further improves its capabilities and strongly outperforms all baselines, with steeper
training curves and better scaling with data. A byte-level 2-stage H-Net overtakes the perplexity of a strong tokenized
Transformer after just 30B training bytes, with the gap widening throughout training, and matches the downstream
evaluations of the tokenized Transformer of twice its size.
Finally, H-Nets realize the benefits of overcoming tokenization:
•
```

### `hnet-v2:s2.2:c0003` p.6 §2.2 Dynamic Chunking (DC) [caption]
```
t !
… n e w _ p r o d u c t !
n e w _ p r o d u c t ! _
n e w _ p r o d u c t ! _
… n e w _ p r o d u c t !
Figure 2: Comparison of decompression strategies on the example sequence "...new product!". indicates a boundary
with high confidence (𝑃𝑡= 1.0) and G# indicates a boundary with low confidence (𝑃𝑡= 0.5). As each letter in the example
is unique, we use the letters in subscripts to denote expected semantics of chunks. (a) Optimal chunking with oracle
boundaries identifying linguistically meaningful units. (b) Suboptimal chunking without a smoothing module. This creates
misalignment during upsampling, causing information from incorrect contexts to propagate. (c) Improved decompression
with a smoothing module, where low-confidence chunks are interpolated with weighted combinations of previous chunks,
correcting the shaded regions. In panels (b) and (c), we interpret low-confidence boundaries cause the encoder network to
embed broader contexts at subsequent positions. Specifically, the vectors at _ and ! encode new_ and duct!, respectively
(instead of w_ and ct!).
differentiable computations by creating smooth interpolations between chunks. Concretely, the smoothing module
```

### `hnet-v2:s5:c0030` p.23 §5 Conclusion [ok]
```
sequences with a standard
sequence model architecture. Since this naive approach suffers from computational challenges on long sequences, Mam-
baByte (Wang et al. 2024) proposed using a state space model for its linear-time efficiency. We similarly use Mamba(-2)
(Dao and Gu 2024) layers in the outer stages of an H-Net. Notably, through extensive ablations we show that Mamba is not
just more efficient but also better at modeling high-resolution data such as text characters and DNA base pairs.
A.1.2
Static Chunking
To reduce sequence length, several approaches downsample the input sequence hierarchically. The most straightforward
methods operate independently of input context, partitioning sequences using fixed-size intervals. Many strategies could
be used to aggregate a width-𝑘window, including direct downsampling, average pooling, linear transformations that mix
across the chunk, convolutions, and more; we lump these together as pooling operations.
Hourglass Transformer (Nawrot, Tworkowski, et al. 2022) and MegaByte (Yu, Simig, et al. 2023) exemplify this strategy.
Other recent variants include the Block Transformer (Ho et al. 2024) and Multiscale Byte Language Model (MBLM)
```

### `hnet-v2:s5:c0026` p.23 §5 Conclusion [ok]
```
Sequences with Multiscale Transformers”. In: Advances in Neural Information Processing Systems 36
(2023), pp. 78808–78823.
[112]
Qihang Yu, Mark Weber, Xueqing Deng, Xiaohui Shen, Daniel Cremers, and Liang-Chieh Chen. “An Image is Worth
32 Tokens for Reconstruction and Generation”. In: Advances in Neural Information Processing Systems 37 (2024),
pp. 128940–128966.
[113]
Yijiong Yu, Ziyun Dai, Zekun Wang, Wei Wang, Ran Chen, and Ji Pei. OpenCSG Chinese Corpus: A Series of High-
quality Chinese Datasets for LLM Training. 2025. arXiv: 2501.08197 [cs.CL]. url: https://arxiv.org/abs/
2501.08197.
[114]
Rowan Zellers, Ari Holtzman, Yonatan Bisk, Ali Farhadi, and Yejin Choi. “HellaSwag: Can a Machine Really Finish
Your Sentence?” In: Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics. 2019.
[115]
Biao Zhang and Rico Sennrich. “Root Mean Square Layer Normalization”. In: Advances in Neural Information
Processing Systems 32 (2019).
Related Work
The fundamental challenge of transforming raw sequential data into computationally efficient representations manifests
across multiple domains through implicit chunking processes. In language modeling, this
```

### `hnet-v2:s2.1:c0005` p.4 §2.1 Architectural Overview [ok]
```
allows straightforward substitution
with alternative architectures (e.g., a state space model, hybrid, or H-Net itself) as explored in our ablations.
Architectural Guidelines.
Compared to standard isotropic models, the H-Net’s structure introduces several new
dimensions of architectural parameters to balance the parameter/compute allocation to each network. To simplify the
search space, we follow a few general guidelines.
7We also sometimes refer to it as a probability—it is interpreted as such in Appendix F—although we do not use it as a formal probability.
• First, we ensure the model width (often referred to as 𝑑model for isotropic architectures) is monotone in the hierarchy:
𝐷0 ≤𝐷1 ≤· · · ≤𝐷𝑆. This allows increasing compute and parameters used in the main network without significantly
increasing its depth.
• Second, using efficient and powerful SSM layers in the outer networks allow reducing the number of layers used
compared to similar prior architectures that only used Transformer layers (Slagle 2024); in this paper, we always
stick to four layers (or the equivalent of four Mamba layers) in each encoder/decoder network.
To handle the changes in dimensions without an
```

### `hnet-v2:s3.3:c0000` p.17 §3.3 Ablation Studies [caption]
```
For ablation studies, we employ H-Net at Large scale following the configurations in Table 1, training on 36B tokens
randomly sampled from FineWeb-Edu.
Importance of Components in H-Net.
Figure 7 illustrates the impact of each architectural component on both model
performance and compression ratio (𝐿𝑠+1/𝐿𝑠) stability during training. We conduct three targeted ablations: (i) using direct
upsampling ˜𝑧𝑡= ˆ𝑧𝑡by removing the smoothing module (w/o smoothing), (ii) replacing the routing module that is based on
scaled cosine similarity, with direct probability prediction from individual inputs (w/o cosine routing), and (iii) skipping the
straight-through estimator in equation (9) (w/o STE).
The smoothing module proves essential for stable training dynamics. Without this module, compression ratios fluctuate
25B
50B
75B
100B
125B
Total Training Bytes
0.80
0.85
0.90
0.95
1.00
1.05
Bits-per-byte (2-stage)
25B
50B
75B
100B
125B
Total Training Bytes
0.34
0.35
0.36
0.37
0.38
Compression Ratio L1/L0
25B
50B
75B
100B
125B
Total Training Bytes
0.36
0.38
0.40
0.42
0.44
Compression Ratio L2/L1
H-Net
w/o smoothing
w/o cosine routing
w/o STE
Figure 7: Ablation study on key H-Net components showing
```

### `hnet-v2:s2.2:c0004` p.6 §2.2 Dynamic Chunking (DC) [ok]
```
the vectors at _ and ! encode new_ and duct!, respectively
(instead of w_ and ct!).
differentiable computations by creating smooth interpolations between chunks. Concretely, the smoothing module applies
an exponential moving average (EMA) with the following definition:
¯𝑧𝑡= 𝑃𝑡ˆ𝑧𝑡+ (1 −𝑃𝑡)¯𝑧𝑡−1.
(5)
Our smoothing module performs several roles:
• Differentiable boundary learning: It transforms the discrete upsampling operation into a continuous one, enabling
effective backpropagation through chunk boundaries during training without requiring stochastic exploration-based
approaches (Jang, Gu, and Poole 2017).
• Adaptive error correction: Chunks with high confidence (𝑃𝑡≈1.0) maintain discrete boundaries (¯𝑧𝑡≈𝑧𝑡),
while chunks with low confidence (𝑃𝑡≈0.5) are smoothed using information from previous chunks, creating a
self-correcting mechanism.
• Training stability: By smoothly interpolating between discrete choices based on confidence scores, a smoothing
module prevents the model from overfitting to suboptimal chunking patterns early in training.
Figure 2 illustrates this with the example "...new product!". The word "product" can be morphologically decomposed
into "pro-" and "-duct"8.
```

## moshi (194 chunks)

### `moshi-v1:s7:c0012` p.41 §7 Conclusion [ok]
```
Dasigi, Nathan Lambert, Kyle Richardson, Jesse Dodge,
Kyle Lo, Luca Soldaini, Noah A. Smith, and Hannaneh Hajishirzi. Olmo: Accelerating
the science of language models. Preprint, 2024. 22
Michael Hassid, Tal Remez, Tu Anh Nguyen, Itai Gat, Alexis Conneau, Felix Kreuk, Jade
Copet, Alexandre D´efossez, Gabriel Synnaeve, Emmanuel Dupoux, Roy Schwartz, and
Yossi Adi. Textually pretrained speech language models. In Alice Oh, Tristan Naumann,
Amir Globerson, Kate Saenko, Moritz Hardt, and Sergey Levine, editors, Advances in
Neural Information Processing Systems 36: Annual Conference on Neural Information
Processing Systems 2023, NeurIPS 2023, New Orleans, LA, USA, December 10 - 16,
2023, 2023. 5, 27, 29
Julien Hauret, Thomas Joubaud, V´eronique Zimpfer, and ´Eric Bavu.
Eben: Extreme
bandwidth extension network applied to speech signals captured with noise-resilient
body-conduction microphones.
In ICASSP 2023-2023 IEEE International Conference
on Acoustics, Speech and Signal Processing (ICASSP), 2023. 11
Dan Hendrycks and Kevin Gimpel. Bridging nonlinearities and stochastic regularizers with
gaussian error linear units. CoRR, abs/1606.08415, 2016a. 10
Dan Hendrycks and Kevin
```

### `moshi-v1:s5.8:c0006` p.31 §5.8 Compressing Moshi and Impact on Speech Quality [caption]
```
ratings on eval-
uating converted speech. Instead, to measure the presence or absence of such degradation
in the audio samples, we first observe that certain audio artifacts are identifiable from the
entropy spectrums of the generated text and audio tokens: A few examples are illustrated
in Figure 6 and we further detail the types of artifacts and their respective detection criteria
in Appendix D.
Following this insight, we measure the presence or absence of different audio artifacts
on the same generated audio samples as the ones used in the previous MOSNet analysis.
We report the results in Table 12, as well as a more detailed per timestep analysis in
Moshi: a speech-text foundation model for real-time dialogue
Table 12: Distribution of audio artifacts caused by model compression. Percentage
of audio artifacts measured in the entropy spectrum of text and speech generated tokens, as
described in Appendix D. These results averaged across 500 samples generated by different
versions of the same quantized Moshi, and across 16 timesteps of 64 tokens. Values of 0 %
are omitted in the table for better readability.
Model / Artifacts
Gibberish
Noisy
Background
Repetitive
No
```

### `moshi-v1:s2:c0006` p.4 §2 Related Work [ok]
```
the integration of acoustic tokens into the same
generative model enables generating arbitrary voices and conditions, rather than a single
speaker. Besides, this hierarchical modeling described in Section 3.4.4 allows decomposing
the generation task without increasing the sequence length of the Transformer (Vaswani
et al., 2017) outputs, unlike Chain-of-Modality. Moreover, Inner Monologue decomposes
speech on a per-frame basis, which means that each prediction step outputs a speech frame.
This is unlike Spectron which requires generating a complete sequence as text before gen-
erating audio tokens, and this makes Moshi compatible with real-time generation. Finally,
we show in Section 3.4.4 how Inner Monologue, when combined with a delay between token
types, allows deriving streaming TTS and ASR systems from Moshi.
Spoken Dialogue Models.
Spoken dialogue is one of the less explored tasks in speech
generation, as it requires addressing several challenges: 1) The model should run in real
time and allow for long conversations in full-duplex—the model always listens and can speak
at any moment; 2) it should be speech-to-speech to handle paralinguistic communication;
3) it should
```

### `moshi-v1:s7:c0015` p.41 §7 Conclusion [ok]
```
Piotr Bojanowski, and Tomas Mikolov. Bag of tricks for
efficient text classification. arXiv preprint arXiv:1607.01759, 2016. 8
Zeqian Ju, Yuancheng Wang, Kai Shen, Xu Tan, Detai Xin, Dongchao Yang, Yanqing
Liu, Yichong Leng, Kaitao Song, Siliang Tang, et al. Naturalspeech 3: Zero-shot speech
synthesis with factorized codec and diffusion models. arXiv preprint arXiv:2403.03100,
2024. 31
Jacob Kahn, Morgane Rivi`ere, Weiyi Zheng, Evgeny Kharitonov, Qiantong Xu, Pierre-
Emmanuel Mazar´e, Julien Karadayi, Vitaliy Liptchinsky, Ronan Collobert, Christian
Fuegen, Tatiana Likhomanenko, Gabriel Synnaeve, Armand Joulin, Abdelrahman Mo-
hamed, and Emmanuel Dupoux. Libri-light: A benchmark for ASR with limited or no
supervision. In IEEE International Conference on Acoustics, Speech and Signal Process-
ing (ICASSP), pages 7669–7673. IEEE, 2020. doi: 10.1109/ICASSP40776.2020.9052942.
Eugene Kharitonov, Damien Vincent, Zal´an Borsos, Rapha¨el Marinier, Sertan Girgin,
Olivier Pietquin, Matt Sharifi, Marco Tagliasacchi, and Neil Zeghidour. Speak, read and
prompt: High-fidelity text-to-speech with minimal supervision. Trans. Assoc. Comput.
Linguistics, 11:1703–1718, 2023. doi: 10.1162/TACL\ A\
```

### `moshi-v1:s3.3.1:c0003` p.9 §3.3.1 Architecture [ok]
```
Mimi is causal and
can be used in a streaming fashion, both for encoding and decoding. Both its initial frame
size and overall stride correspond to 80ms, meaning that given a first audio frame of 80ms,
Mimi outputs a first latent timestep, which can be decoded to 80ms of output audio.
Moshi: a speech-text foundation model for real-time dialogue
Optimization.
Unlike purely convolutional codecs that use Adam (Kingma and Ba,
2015), the introduction of Transformers into the architecture requires additional regular-
ization with weight decay along with using the AdamW (Loshchilov and Hutter, 2019)
optimizer. More precisely, we apply weight decay only to the parameters of the Transform-
ers, with a weight of 5 · 10−2. We use a learning rate of 8 · 10−4, a momentum decay of 0.5
and a decay of the squared gradient of 0.9, and an exponential moving average of weights
with a decay of 0.99. We train with a batch size of 128 on random windows of 12 s, for
4M steps, while the context of Transformers is limited to 10s (250 frames before the last
downsampling layer of the encoder, and symmetrically for the decoder).
Quantization rate.
We use Q = 8 quantizers, each with a codebook size of NA =
```

### `moshi-v1:s4.3:c0001` p.18 §4.3 Speech-Text Instruct data [ok]
```
voice for Moshi during instruction tuning is enough to guarantee almost surely
that it does not use another voice, without further control during inference. In contrast, the
voice of the second audio stream (the user) is randomly sampled for each example, giving
more robustness to different speaking conditions and accents.
To generate the transcripts, we use different prompts, aiming at capturing different
kinds of interactions between a user and Moshi. First, we generate conversations about
general knowledge, by starting from a few Wikipedia paragraphs or StackExchange posts,
which we refer to as context. This ensures that Moshi’s conversations cover a wide range
of topics, such as history, cooking advice or pop culture.
More precisely, using a given context, we obtain a summary of a potential discussion
with the following prompt:
Moshi: a speech-text foundation model for real-time dialogue
{{context}}
Based on information from the previous paragraph, write the summary
of a conversation about {{title}} between Blake and Moshi.
The
summary must be 2 sentences long, and start with "They" or "The
speakers".
where {{context}} refers to paragraphs from Wikipedia or StackExchange and
```

### `moshi-v1:s7:c0032` p.41 §7 Conclusion [ok]
```
generation. arXiv preprint arXiv:2401.13527,
2024a. 29
Xin Zhang, Dong Zhang, Shimin Li, Yaqian Zhou, and Xipeng Qiu. Speechtokenizer: Unified
speech tokenizer for speech language models. In The Twelfth International Conference
on Learning Representations, 2024b. 3, 9, 11, 23
Yizhe Zhang, Siqi Sun, Michel Galley, Yen-Chun Chen, Chris Brockett, Xiang Gao, Jianfeng
Gao, Jingjing Liu, and Bill Dolan.
Dialogpt: Large-scale generative pre-training for
conversational response generation. CoRR, abs/1911.00536, 2019. 30
Yu Zhang, Wei Han, James Qin, Yongqiang Wang, Ankur Bapna, Zhehuai Chen, Nanxin
Chen, Bo Li, Vera Axelrod, Gary Wang, Zhong Meng, Ke Hu, Andrew Rosenberg, Rohit
Prabhavalkar, Daniel S. Park, Parisa Haghani, Jason Riesa, Ginger Perng, Hagen Soltau,
Trevor Strohman, Bhuvana Ramabhadran, Tara N. Sainath, Pedro J. Moreno, Chung-
Cheng Chiu, Johan Schalkwyk, Fran¸coise Beaufays, and Yonghui Wu.
Google USM:
scaling automatic speech recognition beyond 100 languages. CoRR, abs/2303.01037, 2023.
doi: 10.48550/ARXIV.2303.01037. 4
J Zhu. Hidden: hiding data with deep networks. arXiv preprint arXiv:1807.09937, 2018.
Yongxin Zhu, Dan Su, Liqiang He, Linli Xu, and Dong Yu. Generative
```

### `moshi-v1:s7:c0031` p.41 §7 Conclusion [ok]
```
Association, Interspeech 2021,
Brno, Czechia, August 30 - September 3, 2021, pages 1194–1198. ISCA, 2021.
doi:
10.21437/INTERSPEECH.2021-1775. 4
Lili Yu, D´aniel Simig, Colin Flaherty, Armen Aghajanyan, Luke Zettlemoyer, and Mike
Lewis. Megabyte: Predicting million-byte sequences with multiscale transformers. Ad-
vances in Neural Information Processing Systems, 2024. 4, 13
Neil Zeghidour, Alejandro Luebs, Ahmed Omran, Jan Skoglund, and Marco Tagliasacchi.
Soundstream: An end-to-end neural audio codec. IEEE ACM Trans. Audio Speech Lang.
Process., 30, 2022. 3, 4, 9, 10, 11
Rowan Zellers, Ari Holtzman, Yonatan Bisk, Ali Farhadi, and Yejin Choi. Hellaswag: Can
a machine really finish your sentence? arXiv preprint arXiv:1905.07830, 2019. 21
Biao Zhang and Rico Sennrich. Root mean square layer normalization. In Advances in
Neural Information Processing Systems, 2019. 7
Dong Zhang, Xin Zhang, Jun Zhan, Shimin Li, Yaqian Zhou, and Xipeng Qiu. Speechgpt-
gen: Scaling chain-of-information speech generation. arXiv preprint arXiv:2401.13527,
2024a. 29
Xin Zhang, Dong Zhang, Shimin Li, Yaqian Zhou, and Xipeng Qiu. Speechtokenizer: Unified
speech tokenizer for speech language models. In The
```

### `moshi-v1:s7:c0020` p.41 §7 Conclusion [ok]
```
models for consolidating speech recognition/synthesis
and speech/text continuation tasks. ArXiv, abs/2309.07937, 2023. 5, 27, 28
Todor Mihaylov, Peter Clark, Tushar Khot, and Ashish Sabharwal. Can a suit of armor
conduct electricity? a new dataset for open book question answering. arXiv preprint
arXiv:1809.02789, 2018. 21
Kentaro Mitsui, Koh Mitsuda, Toshiaki Wakatsuki, Yukiya Hono, and Kei Sawada. Pslm:
Parallel generation of text and speech with llms for low-latency spoken dialogue systems,
2024. 5
Eliya Nachmani, Alon Levkovitch, Roy Hirsch, Julian Salazar, Chulayuth Asawaroengchai,
Soroosh Mariooryad, Ehud Rivlin, RJ Skerry-Ryan, and Michelle Tadmor Ramanovich.
Spoken question answering and speech continuation using spectrogram-powered LLM. In
The Twelfth International Conference on Learning Representations, 2024. 5, 29
Markus Nagel, Marios Fournarakis, Rana Ali Amjad, Yelysei Bondarenko, Mart van Baalen,
and Tijmen Blankevoort. A white paper on neural network quantization, 2021. 32
Tu Anh Nguyen, Eugene Kharitonov, Jade Copet, Yossi Adi, Wei-Ning Hsu, Ali Elkahky,
Paden Tomasello, Robin Algayres, Benoˆıt Sagot, Abdelrahman Mohamed, and Emmanuel
Dupoux. Generative spoken
```

### `moshi-v1:s7:c0018` p.41 §7 Conclusion [ok]
```
Saehoon Kim, Minsu Cho, and Wook-Shin Han. Autoregressive
image generation using residual quantization. In IEEE/CVF Conference on Computer
Vision and Pattern Recognition, CVPR 2022, New Orleans, LA, USA, June 18-24, 2022,
2022. 4, 13, 14
Jean-Marie Lemercier, Simon Rouard, Jade Copet, Yossi Adi, and Alexandre D´efossez. An
independence-promoting loss for music generation with language models. In ICML, 2024.
Haohe Liu, Ke Chen, Qiao Tian, Wenwu Wang, and Mark D Plumbley. AudioSR: Versatile
audio super-resolution at scale. arXiv preprint arXiv:2309.07314, 2023a. 18
Haohe Liu, Zehua Chen, Yi Yuan, Xinhao Mei, Xubo Liu, Danilo Mandic, Wenwu Wang,
and Mark D Plumbley. AudioLDM: Text-to-audio generation with latent diffusion models.
In Proceedings of the International Conference on Machine Learning, 2023b. 4
Haohe Liu, Xuenan Xu, Yi Yuan, Mengyue Wu, Wenwu Wang, and Mark D Plumbley. Se-
manticodec: An ultra low bitrate semantic audio codec for general sound. arXiv preprint
arXiv:2405.00233, 2024. 23, 24
Team Llama. The llama 3 herd of models. preprint, 2024. 2
Chen-Chou Lo, Szu-Wei Fu, Wen-Chin Huang, Xin Wang, Junichi Yamagishi, Yu Tsao, and
Hsin-Min Wang. Mosnet: Deep learning based
```
