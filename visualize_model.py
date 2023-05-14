import math
import numpy as np
from abc import ABC
from loss_landscapes.model_interface.model_wrapper import wrap_model
from loss_landscapes.model_interface.model_parameters import rand_u_like


class LandscapeWrapper(ABC):
    """
    This abstract class overrides part of the loss_landscapes API (`https://arxiv.org/abs/1712.09913v3`)
     for our paper purposes.
    """
    def get_grid_vectors(self, model, adv_model, deepcopy_model=True, steps=40, distance=1):
        # Model parameters
        model_start_wrapper = wrap_model(self.copy(model) if deepcopy_model else model)
        adv_model_start_wrapper = wrap_model(self.copy(adv_model) if deepcopy_model else adv_model)

        model.set_model_visualization_params()
        adv_model.set_model_visualization_params()

        model_gt = model_start_wrapper.get_module_parameters()
        model_adv = adv_model_start_wrapper.get_module_parameters()

        dir_one = (model_adv - model_gt)

        dir_two = rand_u_like(dir_one)
        # Grahm Shimdt to achieve the orthogonal vector -
        dir_two = dir_two - dir_two.dot(dir_one) * dir_one / math.pow(dir_one.model_norm(2), 2)
        # Equal the vector's norm size
        dir_two = (dir_two / dir_two.model_norm(2)) * dir_one.model_norm(2)

        return dir_one, dir_two

    def linear_interpolation(self, model_start,
                             model_end, x_sig,
                             steps=100, deepcopy_model=False) -> np.ndarray:
        """
        Returns the computed value of the evaluation function applied to the model or
        agent along a linear subspace of the parameter space defined by two end points.
        The models supplied can be either torch.nn.Module models, or ModelWrapper objects
        from the loss_landscapes library for more complex cases.

        That is, given two models, for both of which the model's parameters define a
        vertex in parameter space, the evaluation is computed at the given number of steps
        along the straight line connecting the two vertices. A common choice is to
        use the weights before training and the weights after convergence as the start
        and end points of the line, thus obtaining a view of the "straight line" in
        parameter space from the initialization to some minima. There is no guarantee
        that the model followed this path during optimization. In fact, it is highly
        unlikely to have done so, unless the optimization problem is convex.

        Note that a simple linear interpolation can produce misleading approximations
        of the loss landscape due to the scale invariance of neural networks. The sharpness/
        flatness of minima or maxima is affected by the scale of the neural network weights.
        For more details, see `https://arxiv.org/abs/1712.09913v3`. It is recommended to
        use random_line() with filter normalization instead.

        The Metric supplied has to be a subclass of the loss_landscapes.metrics.Metric class,
        and must specify a procedure whereby the model passed to it is evaluated on the
        task of interest, returning the resulting quantity (such as loss, loss gradient, etc).

        :param model_start: the model defining the start point of the line in parameter space
        :param model_end: the model defining the end point of the line in parameter space
        :param steps: at how many steps from start to end the model is evaluated
        :param deepcopy_model: indicates whether the method will deepcopy the model(s) to avoid aliasing
        :return: 1-d array of loss values along the line connecting start and end models
        """

        # create wrappers from deep copies to avoid aliasing if desired
        model_start_wrapper = wrap_model(self.copy(model_start) if deepcopy_model else model_start)
        end_model_wrapper = wrap_model(self.copy(model_end) if deepcopy_model else model_end)

        start_point = model_start_wrapper.get_module_parameters()
        start_point = start_point - start_point / 2

        end_point = end_model_wrapper.get_module_parameters()
        end_point = end_point + end_point / 2

        direction = (end_point - start_point) / steps

        data_values = []

        s = start_point.parameters[0]
        s.sub_(s / 2)
        data_values.append(model_start.loss_func(s, x_sig))

        for i in range(steps - 1):
            # add a step along the line to the model parameters, then evaluate
            start_point.add_(direction)
            s = start_point.parameters[0]

            data_values.append(model_start.loss_func(s, x_sig))

        return np.array(data_values)

    def random_plane(self, gt_model, adv_model, x, adv_x, distance=3, steps=20, normalization='model',
                     deepcopy_model=False, dir_one=None, dir_two=None) -> np.ndarray:
        """
        Returns the computed value of the evaluation function applied to the model or agent along a planar
        subspace of the parameter space defined by a start point and two randomly sampled directions.
        The models supplied can be either torch.nn.Module models, or ModelWrapper objects
        from the loss_landscapes library for more complex cases.

        That is, given a neural network model, whose parameters define a point in parameter
        space, and a distance, the loss is computed at 'steps' * 'steps' points along the
        plane defined by the two random directions, from the start point up to the maximum
        distance in both directions.

        Note that the dimensionality of the model parameters has an impact on the expected
        length of a uniformly sampled other in parameter space. That is, the more parameters
        a model has, the longer the distance in the random other's direction should be,
        in order to see meaningful change in individual parameters. Normalizing the
        direction other according to the model's current parameter values, which is supported
        through the 'normalization' parameter, helps reduce the impact of the distance
        parameter. In future releases, the distance parameter will refer to the maximum change
        in an individual parameter, rather than the length of the random direction other.

        Note also that a simple planar approximation with randomly sampled directions can produce
        misleading approximations of the loss landscape due to the scale invariance of neural
        networks. The sharpness/flatness of minima or maxima is affected by the scale of the neural
        network weights. For more details, see `https://arxiv.org/abs/1712.09913v3`. It is
        recommended to normalize the directions, preferably with the 'filter' option.

        The Metric supplied has to be a subclass of the loss_landscapes.metrics.Metric class,
        and must specify a procedure whereby the model passed to it is evaluated on the
        task of interest, returning the resulting quantity (such as loss, loss gradient, etc).

        :param gt_model: the model defining the origin point of the plane in parameter space
        :param distance: maximum distance in parameter space from the start point
        :param steps: at how many steps from start to end the model is evaluated
        :param normalization: normalization of direction vectors, must be one of 'filter', 'layer', 'model'
        :param deepcopy_model: indicates whether the method will deepcopy the model(s) to avoid aliasing
        :return: 1-d array of loss values along the line connecting start and end models
        """

        # Copy the relevant models
        gt_model_start_point = wrap_model(self.copy(gt_model) if deepcopy_model else gt_model)

        adv_model_start_wrapper = wrap_model(self.copy(adv_model) if deepcopy_model else adv_model)

        gt_start_point = gt_model_start_point.get_module_parameters()
        adv_start_point = adv_model_start_wrapper.get_module_parameters()

        avg_start_point = (gt_start_point + adv_start_point) / 2

        # scale to match steps and total distance
        dir_one.mul_(distance / steps)
        dir_two.mul_(distance / steps)

        # Move start point so that original start params will be in the center of the plot
        dir_one.mul_(steps / 2)
        dir_two.mul_(steps / 2)

        avg_start_point.sub_(dir_one)
        avg_start_point.sub_(dir_two)

        dir_one.truediv_(steps / 2)
        dir_two.truediv_(steps / 2)

        gt_data_matrix = []
        adv_data_matrix = []
        # evaluate loss in grid of (steps * steps) points, where each column signifies one step
        # along dir_one and each row signifies one step along dir_two. The implementation is again
        # a little convoluted to avoid constructive operations. Fundamentally we generate the matrix
        # [[start_point + (dir_one * i) + (dir_two * j) for j in range(steps)] for i in range(steps].
        for i in range(steps):
            gt_data_column = []
            adv_data_column = []

            for j in range(steps):
                # for every other column, reverse the order in which the column is generated
                # so you can easily use in-place operations to move along dir_two

                if i % 2 == 0:
                    avg_start_point.add_(dir_two)

                    s = avg_start_point.parameters[0]

                    # Do you think is it worth to accumulate average loss? for many sparse signals examples?
                    gt_data_column.append(gt_model.loss_func(s, x))
                    adv_data_column.append(adv_model.loss_func(s, adv_x))

                else:
                    avg_start_point.sub_(dir_two)

                    s = avg_start_point.parameters[0]

                    gt_data_column.insert(0, gt_model.loss_func(s, x))
                    adv_data_column.insert(0, adv_model.loss_func(s, adv_x))

            gt_data_matrix.append(gt_data_column)
            adv_data_matrix.append(adv_data_column)

            avg_start_point.add_(dir_one)

        return np.array(gt_data_matrix), np.array(adv_data_matrix)